// Phase 2 of the Hydronicus Modbus bridge: a Midea heat pump on MQTT.
//
// In cooling, the handover switches zone 1 off instead of on: the wired
// controller knows no dew point, so it must not cool unattended.
//
// It polls the heat pump's holding registers through the Shelly Pro Modbus
// Add-on, publishes them to Home Assistant over MQTT with discovery, and
// executes whitelisted write requests from Home Assistant. It holds no control
// logic of its own except the handover: once Home Assistant's heartbeat has
// been missing for CONFIG.handoverMs, it restores each fallback setting once,
// so the wired controller runs the heat pump by itself, and then writes nothing
// until a heartbeat returns.
//
// Writes are off until CONFIG.writesEnabled is true. Every write reads the
// register first and changes only its own bit or byte, is sent only when the
// value differs, is rate limited per setting and held to a daily budget per
// setting (turning heating or DHW off is exempt from both), and is read back
// after CONFIG.settleMs; the result is published.
//
// Topics, with <base> = CONFIG.base:
//   <base>/state          retained JSON of every mapped value
//   <base>/modbus_healthy retained ON or OFF
//   <base>/handover       retained ON or OFF
//   <base>/write_result   JSON of the last write or refusal
//   <base>/set/<name>     a requested value from Home Assistant
//   <base>/heartbeat      any message from Home Assistant, at least every minute
//
// Shelly scripts have no hoisting, at most 5 timers and 5 RPC calls in
// progress, so Modbus calls go strictly one at a time.

var CONFIG = {
  serialId: 100,
  slaveId: 16, // the address the register scan found
  base: 'hydronicus/midea',
  discoveryPrefix: 'homeassistant',
  pollMs: 10000,
  gapMs: 100,
  rpcTimeoutMs: 10000,
  failuresBeforeUnhealthy: 3,
  writesEnabled: false,
  minWriteIntervalMs: 300000, // per setting
  // The controller keeps written settings across a power cycle, so every write
  // wears its memory: at most this many writes per setting within a day.
  dailyWriteBudget: 50,
  settleMs: 1500, // before the read-back
  handoverMs: 600000, // without a heartbeat
  // Restored once at handover, by the mode the heat pump is set to: heating
  // goes back to the wired controller, cooling stops.
  fallback: { heat: { heating: true }, cool: { heating: false } },
  // t1s takes t1s_cool while the mode is cool; ceilings condense below about 16 °C.
  limits: { t5s: [40, 55], t1s: [25, 50], t1s_cool: [16, 22], curve: [1, 9] },
  republishMs: 60000 // the state is published at least this often, for freshness
};

// The whitelist: each writable setting, its register, and its bits or byte.
var SETTINGS = {
  heating: { reg: 0, mask: 0x0002, kind: 'bit', offSafe: true },
  mode: { reg: 1, mask: 0xffff, kind: 'mode' },
  dhw: { reg: 0, mask: 0x0004, kind: 'bit', offSafe: true },
  curve_enabled: { reg: 5, mask: 0x1000, kind: 'bit' },
  t1s: { reg: 2, mask: 0x00ff, kind: 'byte' },
  curve: { reg: 6, mask: 0x00ff, kind: 'byte' },
  t5s: { reg: 4, mask: 0xffff, kind: 'word' }
};

// The names a request may use, checked as a list so that a topic such as
// set/constructor can never match a property every object inherits.
var NAMES = ['heating', 'mode', 'dhw', 'curve_enabled', 't1s', 'curve', 't5s'];

// The modes a request may set; auto is left to the wired controller, since
// Hydronicus sequences every change between heating and cooling itself.
var MODES = { Heat: 3, Cool: 2 };

function modeName(value) {
  if (value === 3) return 'Heat';
  if (value === 2) return 'Cool';
  if (value === 1) return 'Auto';
  return null;
}

function writable(name) {
  return NAMES.indexOf(name) >= 0;
}

var BLOCKS = [[0, 11], [100, 32]];

var raw = {};
var state = {
  healthy: null,
  failures: 0,
  handover: false,
  heartbeatAt: 0,
  lastWrite: {}, // setting -> uptime ms of its last write
  budget: {}, // setting -> {start: uptime ms its day began, count: writes since}
  queue: [], // pending {name, value, handover}
  job: null, // the write in progress
  handoverFailed: false, // a fallback write of this handover was not confirmed
  published: '',
  publishedAt: 0,
  seq: 0,
  watchdog: null,
  timer: null,
  block: 0,
  ok: false
};

function uptimeMs() {
  return Shelly.getComponentStatus('sys').uptime * 1000;
}

function signed16(v) {
  return v >= 32768 ? v - 65536 : v;
}

function bit(reg, mask) {
  return raw[reg] === undefined ? null : (raw[reg] & mask) !== 0;
}

function lo(reg) {
  return raw[reg] === undefined ? null : raw[reg] & 255;
}

function word(reg) {
  return raw[reg] === undefined ? null : signed16(raw[reg]);
}

function current(name) {
  var s = SETTINGS[name];
  if (s.kind === 'bit') return bit(s.reg, s.mask);
  if (s.kind === 'byte') return lo(s.reg);
  return word(s.reg);
}

function cooling() {
  return word(1) === 2;
}

// What the heat pump does, in words. The operating mode, H:101, reads 3 through a
// DHW run on a 2018 controller and 0 while it switches over, so a DHW run shows
// only as SV1, the valve to the tank coil (H:129 bit 4).
var ACTIVITIES = ['fault', 'defrost', 'standby', 'dhw', 'heating', 'cooling', 'other'];

function activity() {
  var mode = word(101);
  if (mode === null) return null;
  if (word(124)) return 'fault';
  if (bit(128, 0x0002)) return 'defrost';
  if (mode === 0) return 'standby';
  if (bit(129, 0x0010)) return 'dhw';
  if (mode === 3) return 'heating';
  if (mode === 2) return 'cooling';
  return 'other';
}

function snapshot() {
  return {
    heating: bit(0, 0x0002),
    dhw: bit(0, 0x0004),
    mode_set: word(1),
    mode: modeName(word(1)),
    t1s: lo(2),
    t5s: word(4),
    curve_enabled: bit(5, 0x1000),
    curve: lo(6),
    compressor_hz: word(100),
    operating_mode: word(101),
    activity: activity(),
    dhw_valve: bit(129, 0x0010),
    tw_in: word(104),
    tw_out: word(105),
    t4: word(107),
    t1: word(110),
    t5: word(115),
    fault: word(124),
    defrost: bit(128, 0x0002),
    internal_pump: bit(129, 0x0008),
    external_pump: bit(129, 0x0040),
    alarm: bit(129, 0x1000),
    running: bit(129, 0x2000)
  };
}

function publish(topic, message, retain) {
  if (MQTT.isConnected()) MQTT.publish(CONFIG.base + '/' + topic, message, 1, retain);
}

function publishState() {
  // Nothing is published before the first good read: a state of nulls would
  // show every switch off for a moment, which Home Assistant would log and
  // Hydronicus could take for a real change.
  if (raw[0] === undefined || raw[101] === undefined) return;
  var text = JSON.stringify(snapshot());
  // An unchanged state is sent again now and then, so that Home Assistant
  // sees a fresh reading of a temperature that has not moved.
  if (text === state.published && uptimeMs() - state.publishedAt < CONFIG.republishMs) return;
  state.published = text;
  state.publishedAt = uptimeMs();
  publish('state', text, true);
}

function setHealthy(value) {
  if (state.healthy === value) return;
  state.healthy = value;
  print('[bridge] modbus_healthy = ' + value);
  publish('modbus_healthy', value ? 'ON' : 'OFF', true);
}

function report(name, requested, readBack, ok, reason) {
  var result = { name: name, requested: requested, read_back: readBack, ok: ok, reason: reason };
  print('[bridge] write ' + JSON.stringify(result));
  publish('write_result', JSON.stringify(result), false);
}

function later(ms, fn) {
  if (state.timer !== null) Timer.clear(state.timer);
  state.timer = Timer.set(ms, false, function () {
    state.timer = null;
    fn();
  });
}

function stopWatchdog() {
  if (state.watchdog !== null) Timer.clear(state.watchdog);
  state.watchdog = null;
}

// One Modbus call; done(result, error) runs exactly once.
function modbus(method, params, done) {
  state.seq++;
  var seq = state.seq;
  function finish(result, error) {
    if (seq !== state.seq) return;
    state.seq++;
    stopWatchdog();
    done(result, error);
  }
  function onTimeout() {
    state.watchdog = null;
    finish(null, 'no callback');
  }
  function onResult(result, code, message) {
    if (code !== 0) finish(null, 'error ' + code + ': ' + message);
    else finish(result || {}, null);
  }
  params.id = CONFIG.serialId;
  params.sid = CONFIG.slaveId;
  state.watchdog = Timer.set(CONFIG.rpcTimeoutMs, false, onTimeout);
  try {
    Shelly.call('MbRtuClient.' + method, params, onResult);
  } catch (e) {
    finish(null, 'refused: ' + e.message);
  }
}

// The value to write into a register that holds old, or null if invalid.
function encode(s, old, value) {
  if (s.kind === 'bit') return value ? old | s.mask : old & (0xffff ^ s.mask);
  if (s.kind === 'byte') return (old & 0xff00) | (value & 0xff);
  return value & 0xffff; // a word or a mode
}

function parse(name, text) {
  var s = SETTINGS[name];
  if (s.kind === 'bit') {
    if (text === 'ON') return true;
    if (text === 'OFF') return false;
    return null;
  }
  if (s.kind === 'mode') return MODES[text] === 2 || MODES[text] === 3 ? MODES[text] : null;
  var n = Number(text);
  if (!(n === Math.floor(n))) return null;
  // Every numeric setting has limits; one without them is never written.
  var range = name === 't1s' && cooling() ? CONFIG.limits.t1s_cool : CONFIG.limits[name];
  if (!range || !(n >= range[0] && n <= range[1])) return null;
  return n;
}

var DAY_MS = 86400000;

// This setting's day of writes, begun anew once a day has passed.
function budgetDay(name) {
  var day = state.budget[name];
  if (day === undefined || uptimeMs() - day.start >= DAY_MS) {
    day = { start: uptimeMs(), count: 0 };
    state.budget[name] = day;
  }
  return day;
}

// Checks a request; returns why it is refused, or null. A handover write skips
// only the handover, rate, and budget checks.
function refusal(job) {
  var name = job.name;
  var value = job.value;
  var s = SETTINGS[name];
  if (!CONFIG.writesEnabled) return 'writes disabled';
  if (!state.healthy) return 'modbus unhealthy';
  if (state.handover && !job.handover) return 'handover active';
  if (current(name) === value) return 'unchanged';
  var exempt = job.handover || (s.offSafe && value === false);
  var last = state.lastWrite[name];
  if (!exempt && last !== undefined && uptimeMs() - last < CONFIG.minWriteIntervalMs) {
    return 'rate limited for ' + Math.ceil((CONFIG.minWriteIntervalMs - (uptimeMs() - last)) / 1000) + ' s';
  }
  var day = budgetDay(name);
  if (!exempt && day.count >= CONFIG.dailyWriteBudget) {
    return 'daily write budget of ' + CONFIG.dailyWriteBudget + ' used for ' + Math.ceil((DAY_MS - (uptimeMs() - day.start)) / 60000) + ' min';
  }
  return null;
}

// Every write counts against the budget, an exempt one too, since it wears the
// memory just the same.
function rememberWrite(name) {
  state.lastWrite[name] = uptimeMs();
  budgetDay(name).count++;
  try {
    Script.storage.setItem('w', JSON.stringify(state.lastWrite));
    Script.storage.setItem('b', JSON.stringify(state.budget));
  } catch (e) {
    print('[bridge] could not store the write times');
  }
}

// A write runs as a chain of top-level steps on state.job, since deeply nested
// callbacks can crash a Shelly: read, modify only this setting's bits, write,
// wait CONFIG.settleMs, read back, report.
function finishJob() {
  var job = state.job;
  if (job.handover && !job.ok) state.handoverFailed = true;
  state.job = null;
  publishState();
  later(CONFIG.gapMs, step);
}

function afterReadBack(result, error) {
  var job = state.job;
  var s = SETTINGS[job.name];
  if (error) {
    report(job.name, job.value, null, false, 'read-back failed: ' + error);
  } else {
    raw[s.reg] = result.values[0];
    var back = current(job.name);
    job.ok = back === job.value;
    report(job.name, job.value, back, job.ok, job.ok ? 'written' : 'not taken by the heat pump');
  }
  finishJob();
}

function readBack() {
  modbus('ReadHoldingRegisters', { addr: SETTINGS[state.job.name].reg, qty: 1 }, afterReadBack);
}

function afterWrite(result, error) {
  var job = state.job;
  if (error) {
    report(job.name, job.value, current(job.name), false, 'write failed: ' + error);
    finishJob();
    return;
  }
  rememberWrite(job.name);
  later(CONFIG.settleMs, readBack);
}

function afterFreshRead(result, error) {
  var job = state.job;
  var s = SETTINGS[job.name];
  if (error) {
    report(job.name, job.value, null, false, 'read failed: ' + error);
    finishJob();
    return;
  }
  raw[s.reg] = result.values[0];
  var why = refusal(job);
  if (why) {
    job.ok = why === 'unchanged';
    report(job.name, job.value, current(job.name), job.ok, why);
    finishJob();
    return;
  }
  modbus('WriteSingleRegister', { addr: s.reg, value: encode(s, raw[s.reg], job.value) }, afterWrite);
}

// Queues the fallback writes; the handover counts as done only once every one
// of them is confirmed, and endCycle queues them again until then.
function handOver() {
  var fallback = cooling() ? CONFIG.fallback.cool : CONFIG.fallback.heat;
  var names = Object.keys(fallback);
  var i;
  for (i = 0; i < state.queue.length; i++) {
    if (state.queue[i].last) return;
  }
  print('[bridge] no heartbeat for ' + CONFIG.handoverMs / 1000 + ' s: handing over to the wired controller' + (cooling() ? ' with cooling stopped' : ''));
  state.handoverFailed = false;
  for (i = 0; i < names.length; i++) state.queue.push({ name: names[i], value: fallback[names[i]], handover: true });
  state.queue.push({ name: '', last: true });
}

function nextJob() {
  var job = state.queue.splice(0, 1)[0];
  if (job.last) {
    if (state.handoverFailed) {
      print('[bridge] handover not confirmed; retrying next cycle');
    } else {
      state.handover = true;
      publish('handover', 'ON', true);
    }
    later(CONFIG.gapMs, step);
    return;
  }
  state.job = job;
  modbus('ReadHoldingRegisters', { addr: SETTINGS[job.name].reg, qty: 1 }, afterFreshRead);
}

function endCycle() {
  if (state.ok) {
    state.failures = 0;
    setHealthy(true);
    publishState();
  } else {
    state.failures++;
    if (state.failures >= CONFIG.failuresBeforeUnhealthy) setHealthy(false);
  }
  if (!state.handover && CONFIG.writesEnabled && uptimeMs() - state.heartbeatAt > CONFIG.handoverMs) handOver();
  state.block = 0;
  state.ok = false;
  later(state.queue.length ? CONFIG.gapMs : CONFIG.pollMs, step);
}

function onBlock(result, error) {
  var block = BLOCKS[state.block];
  var i;
  if (result && result.values && result.values.length === block[1]) {
    for (i = 0; i < block[1]; i++) raw[block[0] + i] = result.values[i];
    if (state.block === 0) state.ok = true;
  } else if (state.block === 0) {
    print('[bridge] read failed: ' + error);
  }
  state.block++;
  later(CONFIG.gapMs, step);
}

// The sequencer: pending writes first, between blocks, then the next block.
function step() {
  if (state.queue.length) {
    nextJob();
    return;
  }
  if (state.block >= BLOCKS.length || (state.block > 0 && !state.ok)) {
    endCycle();
    return;
  }
  var block = BLOCKS[state.block];
  modbus('ReadHoldingRegisters', { addr: block[0], qty: block[1] }, onBlock);
}

function onSet(topic, message) {
  var name = topic.slice(topic.lastIndexOf('/') + 1);
  if (!writable(name)) {
    report(name, message, null, false, 'not writable');
    return;
  }
  var value = parse(name, message);
  if (value === null) {
    report(name, message, current(name), false, 'invalid or outside limits');
    return;
  }
  state.queue.push({ name: name, value: value });
  // Between polls nothing is in flight, so start at once instead of waiting.
  if (state.job === null && state.watchdog === null) later(CONFIG.gapMs, step);
}

function onHeartbeat() {
  state.heartbeatAt = uptimeMs();
  if (state.handover) {
    state.handover = false;
    print('[bridge] heartbeat returned: Home Assistant has control again');
    publish('handover', 'OFF', true);
  }
}

function discovery(component, object, config) {
  var device = Shelly.getDeviceInfo();
  config.unique_id = device.id + '_midea_' + object;
  config.availability = [{ topic: Shelly.getComponentConfig('mqtt').topic_prefix + '/online', payload_available: 'true', payload_not_available: 'false' }];
  config.device = { identifiers: [device.id + '_midea'], name: 'Midea heat pump', manufacturer: 'Midea' };
  MQTT.publish(CONFIG.discoveryPrefix + '/' + component + '/' + device.id + '_midea/' + object + '/config', JSON.stringify(config), 1, true);
}

// The water temperatures are Hydronicus's condensation reference, and with the
// compressor frequency they feed its no-load guard; it ages a reading by its
// last report. Home Assistant reports an MQTT sensor only when its value
// changes unless force_update is set, so without it a steady reading would
// look stale: cooling would block and the guard would go blind.
var FRESH = ['tw_in', 'tw_out', 'compressor_hz'];

function sensor(object, name, unit, deviceClass) {
  var config = { name: name, state_topic: CONFIG.base + '/state', value_template: '{{ value_json.' + object + ' }}' };
  if (FRESH.indexOf(object) >= 0) config.force_update = true;
  if (unit) config.unit_of_measurement = unit;
  if (deviceClass) {
    config.device_class = deviceClass;
    config.state_class = 'measurement';
  }
  discovery('sensor', object, config);
}

function flag(object, name, deviceClass) {
  discovery('binary_sensor', object, {
    name: name,
    state_topic: CONFIG.base + '/state',
    value_template: "{{ 'ON' if value_json." + object + " else 'OFF' }}",
    device_class: deviceClass
  });
}

function control(component, object, name, extra) {
  var config = { name: name, state_topic: CONFIG.base + '/state', command_topic: CONFIG.base + '/set/' + object };
  var keys = Object.keys(extra);
  var i;
  for (i = 0; i < keys.length; i++) config[keys[i]] = extra[keys[i]];
  discovery(component, object, config);
}

function announce() {
  var t5s = CONFIG.limits.t5s;
  var t1s = CONFIG.limits.t1s;
  var curve = CONFIG.limits.curve;
  control('switch', 'heating', 'Zone 1 heating or cooling', { value_template: "{{ 'ON' if value_json.heating else 'OFF' }}" });
  control('select', 'mode', 'Mode', { value_template: "{{ value_json.mode if value_json.mode in ['Heat', 'Cool'] else 'None' }}", options: ['Heat', 'Cool'] });
  control('switch', 'dhw', 'DHW', { value_template: "{{ 'ON' if value_json.dhw else 'OFF' }}" });
  control('switch', 'curve_enabled', 'Weather curve', { value_template: "{{ 'ON' if value_json.curve_enabled else 'OFF' }}" });
  control('number', 't5s', 'DHW setpoint', { value_template: '{{ value_json.t5s }}', min: t5s[0], max: t5s[1], step: 1, mode: 'box', unit_of_measurement: '°C', device_class: 'temperature' });
  control('number', 't1s', 'Zone 1 water setpoint', { value_template: '{{ value_json.t1s }}', min: CONFIG.limits.t1s_cool[0], max: t1s[1], step: 1, mode: 'box', unit_of_measurement: '°C', device_class: 'temperature' });
  control('number', 'curve', 'Weather curve number', { value_template: '{{ value_json.curve }}', min: curve[0], max: curve[1], step: 1, mode: 'box' });
  sensor('tw_in', 'Water inlet', '°C', 'temperature');
  sensor('tw_out', 'Water outlet', '°C', 'temperature');
  sensor('t4', 'Outdoor', '°C', 'temperature');
  sensor('t1', 'Total water outlet', '°C', 'temperature');
  sensor('t5', 'DHW tank', '°C', 'temperature');
  sensor('compressor_hz', 'Compressor frequency', 'Hz', 'frequency');
  discovery('sensor', 'activity', { name: 'Activity', state_topic: CONFIG.base + '/state', value_template: '{{ value_json.activity }}', device_class: 'enum', options: ACTIVITIES });
  discovery('sensor', 'operating_mode', { name: 'Operating mode code', state_topic: CONFIG.base + '/state', value_template: '{{ value_json.operating_mode }}', entity_category: 'diagnostic' });
  sensor('fault', 'Fault code', null, null);
  flag('internal_pump', 'Internal pump', 'running');
  flag('external_pump', 'External pump', 'running');
  flag('defrost', 'Defrost', 'running');
  flag('dhw_valve', 'DHW valve', 'opening');
  flag('alarm', 'Alarm', 'problem');
  discovery('binary_sensor', 'modbus_healthy', { name: 'Modbus healthy', state_topic: CONFIG.base + '/modbus_healthy', device_class: 'connectivity' });
  discovery('binary_sensor', 'handover', { name: 'Handover to controller', state_topic: CONFIG.base + '/handover' });
  discovery('sensor', 'write_result', { name: 'Last write', state_topic: CONFIG.base + '/write_result', value_template: '{{ value_json.reason }}', json_attributes_topic: CONFIG.base + '/write_result' });
}

function onConnect() {
  print('[bridge] MQTT connected');
  announce();
  state.published = '';
  if (state.healthy !== null) publish('modbus_healthy', state.healthy ? 'ON' : 'OFF', true);
  publish('handover', state.handover ? 'ON' : 'OFF', true);
  publishState();
}

function onHomeAssistantStatus(topic, message) {
  if (message === 'online') onConnect();
}

function main() {
  try {
    var stored = Script.storage.getItem('w');
    if (stored) state.lastWrite = JSON.parse(stored);
  } catch (e) {
    state.lastWrite = {};
  }
  try {
    var budget = Script.storage.getItem('b');
    if (budget) state.budget = JSON.parse(budget);
  } catch (e) {
    state.budget = {};
  }
  // Write times from before a reboot count from now, since uptime restarts;
  // a day of writes keeps its count and begins again now, so a reboot never
  // frees the budget early.
  var names = Object.keys(state.lastWrite);
  var i;
  for (i = 0; i < names.length; i++) state.lastWrite[names[i]] = uptimeMs();
  names = Object.keys(state.budget);
  for (i = 0; i < names.length; i++) state.budget[names[i]].start = uptimeMs();
  state.heartbeatAt = uptimeMs();
  try {
    MQTT.setConnectHandler(onConnect);
    MQTT.subscribe(CONFIG.base + '/set/+', onSet);
    MQTT.subscribe(CONFIG.base + '/heartbeat', onHeartbeat);
    MQTT.subscribe(CONFIG.discoveryPrefix + '/status', onHomeAssistantStatus);
  } catch (e) {
    print('[bridge] MQTT is not enabled: set the broker in the Shelly settings, then start this script again (' + e.message + ')');
    return;
  }
  if (MQTT.isConnected()) onConnect();
  print('[bridge] started; writes ' + (CONFIG.writesEnabled ? 'enabled' : 'disabled'));
  step();
}

main();

/* @meta {"vc":{"healthy":{"type":"boolean","access":"rc","config":{"name":"Modbus healthy","persisted":false,"default_value":false,"meta":{"ui":{"view":"label","titles":["Fault","OK"]}}}}}} */

// Phase 1 of the Hydronicus Modbus bridge: a read-only register scan.
//
// It polls holding registers (FC03) from one Modbus RTU server through the
// Shelly Pro Modbus Add-on, logs every register that changes, and serves the
// latest values and the change history at
//   http://<shelly>/script/<script id>/registers          (JSON)
//   http://<shelly>/script/<script id>/registers?text     (table)
// so the meaning of each register, each bit of H:0 and each byte of H:2 can be
// confirmed by changing a setting on the wired controller and watching it move.
//
// This file sends no register writes: it never calls a Modbus write method, and
// a repository test keeps it that way. The only configuration it may change is
// this Shelly's own Serial component (CONFIG.configureSerial).
//
// Shelly scripts have no hoisting, so every function is defined before use, and
// at most 5 timers and 5 RPC calls per script, so requests run one at a time.

var CONFIG = {
  serialId: 100, // the add-on's Serial / MbRtuClient instance on this Shelly
  baud: 9600,
  format: '8N1',
  configureSerial: true, // set Serial to mb_client with baud and format if it differs
  // The heat pump's Modbus address, set by rotary switch S3, or 0 to search
  // searchFrom..searchTo for the address that answers, trying the address
  // found last time first.
  slaveId: 0,
  searchFrom: 1,
  searchTo: 247,
  searchRetryMs: 60000, // pause before searching again when no address answered
  // [first register, count] read with one FC03 request each (count 1..123).
  // The first block is the health probe; a later block that fails is read one
  // register at a time, so an unsupported address only marks itself.
  blocks: [[0, 11], [100, 41], [200, 10]],
  pollMs: 10000, // pause between completed cycles
  gapMs: 100, // pause between requests
  rpcTimeoutMs: 10000, // a call whose callback has not come by then counts as lost
  failuresBeforeUnhealthy: 3, // consecutive failed probes
  historySize: 40, // register changes kept for the endpoint
  logChanges: true
};

var HEX = '0123456789ABCDEF';

var state = {
  raw: {}, // address -> last value read
  errors: {}, // address -> last error message
  changes: {}, // address -> number of changes seen
  changedAt: {}, // address -> unix time of the last change
  history: [], // {t, a, from, to}
  single: {}, // block index -> true once that block is read register by register
  healthy: null,
  probeFailures: 0,
  cycles: 0,
  lastOk: null,
  serial: 'unchecked',
  slave: null, // the address being read
  search: 'off', // off, searching, found, or none
  seq: 0,
  watchdog: null,
  timer: null
};

var healthyVc = null;

function now() {
  return Math.floor(Date.now() / 1000);
}

function hex4(v) {
  var s = '';
  var i;
  for (i = 12; i >= 0; i -= 4) s += HEX.charAt((v >> i) & 15);
  return '0x' + s;
}

function bin16(v) {
  var s = '';
  var i;
  for (i = 15; i >= 0; i--) {
    s += (v >> i) & 1 ? '1' : '0';
    if (i % 4 === 0 && i > 0) s += '_';
  }
  return s;
}

function signed16(v) {
  return v >= 32768 ? v - 65536 : v;
}

function describe(v) {
  return v + ' ' + hex4(v) + ' ' + bin16(v) + ' s=' + signed16(v) + ' lo=' + (v & 255) + ' hi=' + ((v >> 8) & 255);
}

function setHealthy(value) {
  if (state.healthy === value) return;
  state.healthy = value;
  print('[scan] modbus_healthy = ' + value);
  if (healthyVc) healthyVc.setValue(value);
}

function record(address, value) {
  var old = state.raw[address];
  delete state.errors[address];
  if (old === value) return;
  state.raw[address] = value;
  if (old === undefined) return;
  state.changes[address] = (state.changes[address] || 0) + 1;
  state.changedAt[address] = now();
  state.history.push({ t: now(), a: address, from: old, to: value });
  if (state.history.length > CONFIG.historySize) state.history.splice(0, 1);
  if (CONFIG.logChanges) print('[scan] H:' + address + ' ' + describe(old) + ' -> ' + describe(value));
}

function recordError(first, count, message) {
  var i;
  for (i = 0; i < count; i++) state.errors[first + i] = message;
}

function stopWatchdog() {
  if (state.watchdog !== null) Timer.clear(state.watchdog);
  state.watchdog = null;
}

// Reads count registers from first and calls done(values, error) exactly once.
// Requests go one at a time, each after the previous call's callback: the
// add-on holds a request to a quiet address until its own timeout, and the
// firmware refuses more than 5 calls in progress. The watchdog only gives up
// on a callback that never comes, and a refused call is reported, not thrown.
function readRegisters(first, count, done) {
  state.seq++;
  var seq = state.seq;
  function finish(values, error) {
    if (seq !== state.seq) return;
    state.seq++;
    stopWatchdog();
    done(values, error);
  }
  function onTimeout() {
    state.watchdog = null;
    finish(null, 'no callback');
  }
  function onResult(result, code, message) {
    if (code !== 0) {
      finish(null, 'error ' + code + ': ' + message);
    } else if (!result || !result.values || result.values.length !== count) {
      finish(null, 'short or empty response');
    } else {
      finish(result.values, null);
    }
  }
  state.watchdog = Timer.set(CONFIG.rpcTimeoutMs, false, onTimeout);
  try {
    Shelly.call(
      'MbRtuClient.ReadHoldingRegisters',
      { id: CONFIG.serialId, sid: state.slave, addr: first, qty: count },
      onResult
    );
  } catch (e) {
    finish(null, 'refused: ' + e.message);
  }
}

function later(ms, fn) {
  if (state.timer !== null) Timer.clear(state.timer);
  state.timer = Timer.set(ms, false, function () {
    state.timer = null;
    fn();
  });
}

var cycle = { block: 0, offset: 0, probeOk: false };

function nextBlock() {
  cycle.block++;
  cycle.offset = 0;
  later(CONFIG.gapMs, readNext);
}

function endCycle() {
  state.cycles++;
  if (cycle.probeOk) {
    state.probeFailures = 0;
    state.lastOk = now();
    setHealthy(true);
  } else {
    state.probeFailures++;
    if (state.probeFailures >= CONFIG.failuresBeforeUnhealthy) setHealthy(false);
  }
  if (state.cycles === 1) print('[scan] first cycle done; registers at /script/' + Shelly.getCurrentScriptId() + '/registers');
  later(CONFIG.pollMs, startCycle);
}

function onBlock(values, error) {
  var first = CONFIG.blocks[cycle.block][0];
  var count = CONFIG.blocks[cycle.block][1];
  var i;
  if (values) {
    for (i = 0; i < count; i++) record(first + i, values[i]);
    if (cycle.block === 0) cycle.probeOk = true;
    nextBlock();
    return;
  }
  recordError(first, count, error);
  if (cycle.block > 0 && cycle.probeOk && count > 1) {
    print('[scan] block H:' + first + '+' + count + ' failed (' + error + '); reading it one register at a time');
    state.single[cycle.block] = true;
  } else if (cycle.block === 0) {
    print('[scan] probe H:' + first + '+' + count + ' failed: ' + error);
  }
  nextBlock();
}

function onSingle(values, error) {
  var address = CONFIG.blocks[cycle.block][0] + cycle.offset;
  if (values) record(address, values[0]);
  else state.errors[address] = error;
  cycle.offset++;
  if (cycle.offset >= CONFIG.blocks[cycle.block][1]) nextBlock();
  else later(CONFIG.gapMs, readNext);
}

function readNext() {
  if (cycle.block >= CONFIG.blocks.length) {
    endCycle();
    return;
  }
  var block = CONFIG.blocks[cycle.block];
  // Once the probe has failed this cycle the bus is down; skip the other blocks.
  if (cycle.block > 0 && !cycle.probeOk) {
    endCycle();
    return;
  }
  if (state.single[cycle.block]) readRegisters(block[0] + cycle.offset, 1, onSingle);
  else readRegisters(block[0], block[1], onBlock);
}

function startCycle() {
  cycle.block = 0;
  cycle.offset = 0;
  cycle.probeOk = false;
  readNext();
}

// The address search: one FC03 read of the first block's first register at
// each address, the remembered one first; the first address that answers wins.
var search = { order: [], index: 0, lastError: null };

function remembered() {
  try {
    var value = Script.storage.getItem('slave');
    return value === null || value === undefined ? null : Number(value);
  } catch (e) {
    return null;
  }
}

function remember(address) {
  try {
    Script.storage.setItem('slave', String(address));
  } catch (e) {
    print('[scan] could not remember address ' + address);
  }
}

function probeNext() {
  if (search.index >= search.order.length) {
    state.search = 'none';
    print('[scan] no address in ' + CONFIG.searchFrom + '..' + CONFIG.searchTo + ' answered (last: ' + search.lastError + '); check wiring, A/B polarity, baud and format; searching again in ' + CONFIG.searchRetryMs / 1000 + ' s');
    later(CONFIG.searchRetryMs, startSearch);
    return;
  }
  state.slave = search.order[search.index];
  readRegisters(CONFIG.blocks[0][0], 1, onProbe);
}

function onProbe(values, error) {
  if (values) {
    state.search = 'found';
    remember(state.slave);
    print('[scan] address ' + state.slave + ' answers; reading it');
    later(CONFIG.gapMs, startCycle);
    return;
  }
  // The add-on's error codes are not documented, so only values count as an
  // answer; the last error is reported if no address answers.
  search.lastError = error;
  // A refused call never reached the bus, so the same address is tried again.
  if (error && error.indexOf('refused') === 0) {
    later(1000, probeNext);
    return;
  }
  search.index++;
  later(CONFIG.gapMs, probeNext);
}

function startSearch() {
  var first = remembered();
  var order = [];
  var a;
  if (first !== null && first >= CONFIG.searchFrom && first <= CONFIG.searchTo) order.push(first);
  for (a = CONFIG.searchFrom; a <= CONFIG.searchTo; a++) {
    if (a !== first) order.push(a);
  }
  search.order = order;
  search.index = 0;
  state.search = 'searching';
  print('[scan] searching addresses ' + CONFIG.searchFrom + '..' + CONFIG.searchTo + (first !== null ? ', ' + first + ' first' : ''));
  probeNext();
}

function begin() {
  if (CONFIG.slaveId > 0) {
    state.slave = CONFIG.slaveId;
    startCycle();
  } else {
    startSearch();
  }
}

function addresses() {
  var list = [];
  var b;
  var i;
  for (b = 0; b < CONFIG.blocks.length; b++) {
    for (i = 0; i < CONFIG.blocks[b][1]; i++) list.push(CONFIG.blocks[b][0] + i);
  }
  return list;
}

function asText() {
  var lines = [
    'slave ' + state.slave + ' (search ' + state.search + ')  healthy ' + state.healthy + '  cycles ' + state.cycles + '  last ok ' + state.lastOk + '  serial ' + state.serial,
    'addr  dec    hex     bits                 signed  lo   hi   changes  error'
  ];
  var list = addresses();
  var i;
  var a;
  var v;
  for (i = 0; i < list.length; i++) {
    a = list[i];
    v = state.raw[a];
    if (v === undefined) {
      lines.push('H:' + a + '  -  ' + (state.errors[a] || 'not read'));
    } else {
      lines.push(
        'H:' + a + '  ' + v + '  ' + hex4(v) + '  ' + bin16(v) + '  ' + signed16(v) + '  ' + (v & 255) + '  ' + ((v >> 8) & 255) + '  ' + (state.changes[a] || 0) + '  ' + (state.errors[a] || '')
      );
    }
  }
  lines.push('');
  lines.push('changes (oldest first):');
  for (i = 0; i < state.history.length; i++) {
    a = state.history[i];
    lines.push(a.t + '  H:' + a.a + '  ' + describe(a.from) + '  ->  ' + describe(a.to));
  }
  return lines.join('\n');
}

function asJson() {
  var registers = [];
  var list = addresses();
  var i;
  for (i = 0; i < list.length; i++) {
    registers.push({
      a: list[i],
      v: state.raw[list[i]] === undefined ? null : state.raw[list[i]],
      n: state.changes[list[i]] || 0,
      t: state.changedAt[list[i]] || null,
      e: state.errors[list[i]] || null
    });
  }
  return JSON.stringify({
    slave: state.slave,
    search: state.search,
    healthy: state.healthy,
    cycles: state.cycles,
    last_ok: state.lastOk,
    serial: state.serial,
    registers: registers,
    history: state.history
  });
}

function onRequest(request, response) {
  if (request.query && request.query.indexOf('text') === 0) {
    response.body = asText();
  } else {
    response.body = asJson();
    response.headers = [['Content-Type', 'application/json']];
  }
  response.code = 200;
  response.send();
}

function validConfig() {
  var b;
  if (CONFIG.slaveId < 0 || CONFIG.slaveId > 247 || CONFIG.slaveId !== Math.floor(CONFIG.slaveId)) return 'slaveId must be 0 (search) or 1..247';
  if (CONFIG.searchFrom < 1 || CONFIG.searchTo > 247 || CONFIG.searchFrom > CONFIG.searchTo) return 'search range must lie within 1..247';
  if (!CONFIG.blocks.length) return 'blocks must not be empty';
  for (b = 0; b < CONFIG.blocks.length; b++) {
    if (CONFIG.blocks[b][1] < 1 || CONFIG.blocks[b][1] > 123) return 'a block reads 1..123 registers';
  }
  if (CONFIG.pollMs < 1000 || CONFIG.gapMs < 20 || CONFIG.rpcTimeoutMs < 500) return 'timings too short';
  return null;
}

function onSerialSet(result, code, message) {
  if (code !== 0) {
    state.serial = 'set failed: ' + message;
    print('[scan] Serial.SetConfig failed: ' + message);
    return;
  }
  if (result && result.restart_required) {
    state.serial = 'reboot required';
    print('[scan] Serial reconfigured; reboot the Shelly, then start this script again');
    return;
  }
  state.serial = 'configured';
  begin();
}

function onSerialConfig(result, code, message) {
  if (code !== 0 || !result) {
    state.serial = 'unreadable: ' + message;
    print('[scan] Serial ' + CONFIG.serialId + ' unreadable (' + message + '); is the Modbus add-on enabled?');
    return;
  }
  var ok = result.mode === 'mb_client' && result.serial && result.serial.baud === CONFIG.baud && result.serial.format === CONFIG.format;
  if (ok) {
    state.serial = 'ok';
    begin();
    return;
  }
  print('[scan] Serial ' + CONFIG.serialId + ' is ' + JSON.stringify(result));
  if (!CONFIG.configureSerial) {
    state.serial = 'mismatch';
    print('[scan] set it to mb_client ' + CONFIG.baud + ' ' + CONFIG.format + ', or set configureSerial: true');
    return;
  }
  Shelly.call(
    'Serial.SetConfig',
    { id: CONFIG.serialId, config: { mode: 'mb_client', serial: { baud: CONFIG.baud, format: CONFIG.format } } },
    onSerialSet
  );
}

function main() {
  var problem = validConfig();
  if (problem) {
    print('[scan] invalid CONFIG: ' + problem);
    return;
  }
  healthyVc = Script.getVcHandle('healthy');
  if (!healthyVc) print('[scan] no managed "healthy" component; health is only logged');
  setHealthy(false);
  HTTPServer.registerEndpoint('registers', onRequest);
  Shelly.call('Serial.GetConfig', { id: CONFIG.serialId }, onSerialConfig);
}

main();

"""The Midea Shelly Modbus adapter keeps the promises its README makes."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ADAPTER = Path(__file__).parents[1] / "adapters" / "midea-shelly-modbus"
SCAN = ADAPTER / "modbus-scan.shelly.js"


def test_the_scan_script_can_never_write_a_register() -> None:
    source = SCAN.read_text(encoding="utf-8")

    assert "Write" not in source
    methods = set(re.findall(r"'((?:MbRtuClient|Serial)\.\w+)'", source))
    assert methods == {"MbRtuClient.ReadHoldingRegisters", "Serial.GetConfig", "Serial.SetConfig"}


def test_the_scan_script_declares_its_health_component_on_the_first_line() -> None:
    first = SCAN.read_text(encoding="utf-8").splitlines()[0]

    match = re.fullmatch(r"/\* @meta (.*) \*/", first)
    assert match is not None
    meta = json.loads(match.group(1))
    healthy = meta["vc"]["healthy"]
    assert healthy["type"] == "boolean"
    assert healthy["config"]["meta"]["ui"]["view"] == "label"


BRIDGE = ADAPTER / "midea-bridge.shelly.js"


def test_the_bridge_writes_only_whitelisted_registers_with_single_register_writes() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    methods = set(re.findall(r"modbus\('(\w+)'", source))
    assert methods == {"ReadHoldingRegisters", "WriteSingleRegister"}
    assert "MbRtuClient.Write" not in source, "every call goes through modbus()"
    settings = re.search(r"var SETTINGS = \{(.*?)\n\};", source, re.DOTALL)
    assert settings is not None
    registers = {int(reg) for reg in re.findall(r"reg: (\d+)", settings.group(1))}
    assert registers == {0, 1, 2, 4, 5, 6}


def test_the_bridge_ships_with_writes_off() -> None:
    assert "writesEnabled: false," in BRIDGE.read_text(encoding="utf-8")


def test_the_bridge_checks_request_names_against_its_list_not_object_properties() -> None:
    source = BRIDGE.read_text(encoding="utf-8")

    names = re.search(r"var NAMES = \[(.*?)\];", source)
    settings = re.search(r"var SETTINGS = \{(.*?)\n\};", source, re.DOTALL)
    assert names is not None and settings is not None
    assert set(re.findall(r"'(\w+)'", names.group(1))) == set(
        re.findall(r"^\s+(\w+): \{", settings.group(1), re.MULTILINE)
    )
    assert "if (!writable(name))" in source
    assert "!SETTINGS[" not in source


# Runs the bridge in Node with the Shelly APIs stubbed, then evaluates checks
# against its own state. The script's main() starts, but no timer ever fires.
HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[2], 'utf8')
  .replace('writesEnabled: false,', 'writesEnabled: true,');
const store = {};
let uptime = 1000;
function load() {
  const context = {
    print: () => {},
    JSON, Math, Number, Object,
    Shelly: {
      getComponentStatus: () => ({ uptime: uptime / 1000 }),
      getComponentConfig: () => ({ topic_prefix: 'shelly' }),
      getDeviceInfo: () => ({ id: 'shelly', model: 'Pro 3EM' }),
      call: () => {},
    },
    Script: { storage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } } },
    MQTT: {
      setConnectHandler: () => {}, subscribe: () => {}, publish: () => {},
      isConnected: () => false,
    },
    Timer: { set: () => 1, clear: () => {} },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  vm.runInContext('state.healthy = true; raw[0] = 2; raw[4] = 50;', context);
  return context;
}
const run = (context, code) => vm.runInContext(code, context);
const results = {};
let bridge = load();
const t5s = "refusal({ name: 't5s', value: 49 })";
for (let i = 0; i < 50; i++) {
  uptime += 360000;
  run(bridge, "rememberWrite('t5s'); rememberWrite('heating')");
}
uptime += 360000;
results.spent = run(bridge, t5s);
results.offExempt = run(bridge, "refusal({ name: 'heating', value: false })");
results.handoverExempt = run(bridge, "refusal({ name: 't5s', value: 49, handover: true })");
uptime += 86400000;
results.nextDay = run(bridge, t5s);
for (let i = 0; i < 50; i++) {
  uptime += 360000;
  run(bridge, "rememberWrite('t5s')");
}
uptime = 1000;
bridge = load();
uptime += 360000;
results.afterReboot = run(bridge, t5s);
console.log(JSON.stringify(results));
"""


def test_the_bridge_holds_each_setting_to_its_daily_write_budget(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("the bridge's behavior runs in Node")
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")

    output = subprocess.run(
        [node, str(harness), str(BRIDGE)], capture_output=True, text=True, check=True
    ).stdout
    results = json.loads(output)

    assert results["spent"].startswith("daily write budget of 50 used for ")
    assert results["offExempt"] is None
    assert results["handoverExempt"] is None
    assert results["nextDay"] is None
    assert results["afterReboot"].startswith("daily write budget of 50 used for 1434 min")


# Drives one request at a time through the bridge's write steps: the fresh
# read is answered with the register as it stands, and every Modbus call and
# report is recorded. The window is 30 s from the last write of a setting.
HOLD_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[2], 'utf8')
  .replace('writesEnabled: false,', 'writesEnabled: true,');
let uptime = 1000;
const calls = [];
const reports = [];
const context = {
  print: (line) => {
    if (line.startsWith('[bridge] write ')) reports.push(JSON.parse(line.slice(15)));
  },
  JSON, Math, Number, Object,
  Shelly: {
    getComponentStatus: () => ({ uptime: uptime / 1000 }),
    getComponentConfig: () => ({ topic_prefix: 'shelly' }),
    getDeviceInfo: () => ({ id: 'shelly', model: 'Pro 3EM' }),
    call: (method) => { calls.push(method); },
  },
  Script: { storage: { getItem: () => null, setItem: () => {} } },
  MQTT: {
    setConnectHandler: () => {}, subscribe: () => {}, publish: () => {},
    isConnected: () => false,
  },
  Timer: { set: () => 1, clear: () => {} },
};
vm.createContext(context);
vm.runInContext(source, context);
const run = (code) => vm.runInContext(code, context);
run('state.healthy = true; raw[0] = 2; raw[5] = 4096;');
// One request: queued, started, its fresh read answered; returns its report.
function request(name, value) {
  calls.length = 0;
  run(`state.queue = [{ name: '${name}', value: ${value} }]; nextJob();`);
  run(`afterFreshRead({ values: [raw[SETTINGS['${name}'].reg]] }, null);`);
  return {
    report: reports[reports.length - 1],
    wrote: calls.includes('MbRtuClient.WriteSingleRegister'),
  };
}
const results = {};
results.first = request('curve_enabled', false);
run("rememberWrite('curve_enabled'); state.job = null;");
uptime += 5000;
results.early = request('curve_enabled', false);
results.heldAfterEarly = run('JSON.stringify(state.held)');
uptime += 5000;
results.backToCurrent = request('curve_enabled', true);
results.heldAfterBack = run('JSON.stringify(state.held)');
request('curve_enabled', false);
uptime += 25000;
run('releaseHeld()');
results.released = run('JSON.stringify(state.queue)');
results.heldAfterRelease = run('JSON.stringify(state.held)');
run("rememberWrite('heating'); state.queue = [];");
results.heatingOff = request('heating', false);
run("state.job = null; rememberWrite('t5s'); raw[4] = 50;");
request('t5s', 49);
run('handOver()');
results.heldAfterHandover = run('JSON.stringify(state.held)');
console.log(JSON.stringify(results));
"""


def test_the_bridge_holds_a_quick_change_and_writes_the_latest_once_its_window_ends(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("the bridge's behavior runs in Node")
    harness = tmp_path / "hold.js"
    harness.write_text(HOLD_HARNESS, encoding="utf-8")

    output = subprocess.run(
        [node, str(harness), str(BRIDGE)], capture_output=True, text=True, check=True
    ).stdout
    results = json.loads(output)

    assert results["first"]["wrote"], "nothing written before: no window"
    assert not results["early"]["wrote"]
    assert results["early"]["report"]["reason"] == "held for 25 s"
    assert json.loads(results["heldAfterEarly"]) == [{"name": "curve_enabled", "value": False}]
    assert results["backToCurrent"]["report"]["reason"] == "unchanged"
    assert json.loads(results["heldAfterBack"]) == [], "a newer request replaces the held one"
    assert json.loads(results["released"]) == [{"name": "curve_enabled", "value": False}]
    assert json.loads(results["heldAfterRelease"]) == []
    assert results["heatingOff"]["wrote"], "turning heating off never waits"
    assert json.loads(results["heldAfterHandover"]) == []

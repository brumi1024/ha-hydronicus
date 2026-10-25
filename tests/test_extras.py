"""The Shelly bridge scripts keep the promises their README makes."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

EXTRAS = Path(__file__).parents[1] / "extras" / "shelly-modbus-bridge"
SCAN = EXTRAS / "modbus-scan.shelly.js"


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


BRIDGE = EXTRAS / "midea-bridge.shelly.js"


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

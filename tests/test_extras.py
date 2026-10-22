"""The Shelly bridge scripts keep the promises their README makes."""

from __future__ import annotations

import json
import re
from pathlib import Path

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

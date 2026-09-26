---
name: Diagnostic bug report
about: Report a reproducible Hydronicus problem with redacted diagnostic context
title: "[Bug]: "
labels: bug
assignees: ""
---

## Before submitting

- [ ] I reproduced this with synthetic entities, or with Control equipment off.
- [ ] I removed credentials, tokens, private addresses, hostnames, and household-specific entity details.
- [ ] I reviewed the diagnostics, which keep entity IDs and area IDs, before attaching any part of them.
- [ ] I searched existing issues for the same symptom.

## Summary

Describe the observed problem in one or two sentences.

## Versions

- Hydronicus version or commit:
- Home Assistant version:
- HACS version, if applicable:
- Installation method: `HACS custom repository` / `source checkout` / `other`

## Reproduction

Describe the smallest Plant that reproduces the problem, ideally as a redacted plant file.
Use logical names such as `zone_a`, `loop_a`, `switch.valve_a`, and `switch.pump_a`.

1.
2.
3.

## Expected behavior

Describe what Hydronicus should decide or show.

## Actual behavior

Describe what Hydronicus decided or showed instead.
Include the relevant state and attributes of the Status sensor, such as `reasons`, `blocked_zones`, and `proposed`, and any Repair.

## Plant file

```yaml
hydronicus: 2
name: Example
pumps:
  pump_a:
    switch: switch.pump_a
zones:
  zone_a:
    temperature: [sensor.zone_a_temperature]
    loops:
      loop_a:
        valves: [switch.valve_a]
        pump: pump_a
```

## Sensor and output states

Provide only generic, redacted values.

```text
Plant mode: heat
Control equipment: off
zone_a temperature: 18.0 °C, target 21.0 °C, thermostat heat
zone_a heating demand: on
switch.valve_a: on
switch.pump_a: off
Status: heating
```

## Logs

Paste the smallest relevant redacted log excerpt.
Include the first exception and a short traceback when available.

```text
Paste redacted logs here.
```

## Additional context

Mention whether the problem survived a reload, and whether it reproduces with a clean synthetic Plant.
Do not attach full backups, unreviewed diagnostics, private configuration files, or unredacted screenshots.

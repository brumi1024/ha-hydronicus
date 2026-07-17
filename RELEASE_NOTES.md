# Hydronicus {{VERSION}}

## Upgrade

Back up the Home Assistant configuration before upgrading.

Install this release through HACS, restart Home Assistant, and confirm that the Hydronicus config entry reloads without errors.

New plants remain in shadow mode until their compiled topology and explanations have been reviewed.

## Rollback

If the integration does not load correctly, restore the previous HACS release and restart Home Assistant.

Keep physical temperature, condensation, pressure, and flow safeguards independently active during any rollback.

## Known limitations

This release is shadow-mode software and does not issue physical actuator service calls.

Active equipment control, safety interlocks, heating and cooling changeover, source coordination, diagnostics, and repairs remain limited or planned while the public beta matures.

## Hydronicus rename boundary

Hydronicus is installed from `custom_components/hydronicus` and uses the `hydronicus` domain.

The former `hydronic_climate` integration name and domain are not supported and must not be recreated during an upgrade.

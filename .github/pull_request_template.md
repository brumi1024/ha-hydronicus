## What and why

<!--
Two to four sentences: the problem or goal, and what this change does about it.
Write for a reviewer who has not seen your branch.
Link the issue if there is one: Fixes #123.
Do not list files or restate the diff; the diff is right there.
-->

## Behaviour change

<!--
What a user or an existing Plant notices: new or changed entities, plant file keys, UI forms, Repairs, defaults, or control decisions.
Name anything that needs the user to act on update, such as setting a Plant up again.
Write "None" for a refactor, test, docs, or CI change.
-->

## Safety

<!--
Answer only if the change touches control decisions, sequencing, condensation, frost, arming, Dry run, or commands sent to equipment.
Name the invariants in docs/architecture.md it affects and the test that holds each one.
Delete this section otherwise.
-->

## How it was checked

<!--
The tests that prove the change, by name or file, and anything checked by hand, such as a live Home Assistant with the trial kit.
`make verify` passing is assumed; say so only if it did not pass, and why.
Do not paste test counts, coverage numbers, or command output.
-->

## Checklist

- [ ] A test fails without this change, or the change is docs, CI, or a refactor.
- [ ] New or renamed plant file keys are in `docs/examples/full-plant.yaml`.
- [ ] UI string changes are in `strings.json` and copied to `translations/en.json`.
- [ ] A user-facing change has a line in `docs/releases/v<next version>.md`.

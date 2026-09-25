"""The setup, reconfigure, zone, and Plant settings flows (contract K8).

Every flow edits a plant file document, the same schema as storage, and checks
the whole resulting Plant with ``core.plant_file`` after each form, so a zone
change goes through the same validation as setup (invariant 9).

- ``documents`` reads form values from a document and writes them back,
  keeping the settings a form does not show.
- ``forms`` builds the forms and turns a plant file problem into a form error.
- ``plant`` is the config flow: guided setup, import, and entry reconfigure.
- ``zone`` is the zone subentry flow, and ``settings`` the Plant settings.
"""

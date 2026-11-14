# GhostUI

Main application for capability-driven interface generation. The existing
`marshall-acton3-ble` folder remains the hardware integration and diagnostics.
No files inside that folder are changed by this app.

## Run

From this folder, use the existing environment:

```sh
marshall-acton3-ble/.venv/bin/python app.py --simulate
```

Open http://127.0.0.1:8780. Simulation is visibly labeled.
For the speaker, close other BLE scripts and the Marshall app, then run:

```sh
marshall-acton3-ble/.venv/bin/python app.py
```

An optional explicit BLE address is also accepted. Auto-discovery reuses the
verified legacy Acton III integration. Initial state must load before controls
are enabled. Refresh state is manual; slider changes send on release.

## AI generation

Set `OPENAI_API_KEY` in your terminal environment before starting the app.
Do not paste the key into source files, the browser, or chat. An optional
`OPENAI_MODEL` overrides the default `gpt-4.1-mini`; it must support Chat
Completions structured outputs. API access/billing is separate from this code.
The app uses Python's standard HTTP client; no additional AI SDK is needed.

Click **Generate interface** and enter a style preference. Only device
capabilities and the preference are sent to the API. Credentials stay on the
server. The model chooses title, ordering, labels and groups; range limits,
command endpoints and hardware behavior remain under adapter control.

All supported controls must appear exactly once as sliders. Unknown bindings,
extra fields, duplicates and malformed results are rejected. A failed model
call or missing key returns a visibly labeled deterministic template. Starting
without a key is useful for testing, but is not AI generation.

## Current limits

This is a local browser prototype, not AR yet. It reuses `Adapter`, `CAPS` and
the control-page components from `marshall-acton3-ble/ghostui.py` as an explicit
integration dependency. Generation lives in `interface_generation.py`.
The app binds only to localhost and uses separate session tokens for device
commands and generation. BLE tasks execute serially on one worker. Avoid
running other speaker-control servers at the same time.

Actual speaker writes are already exercised by the earlier prototype; this
main application's Bluetooth thread still needs a hardware smoke test.
# hackumass2026
# hackumass2026

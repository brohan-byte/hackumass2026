# GhostUI architecture

## Layout

- `app.py`: stable command-line entry point. Existing launch arguments still work.
- `ghostui_backend/cli.py`: server startup and LAN pairing.
- `ghostui_backend/contracts.py`: adapter protocol and integer capability validation.
- `ghostui_backend/registry.py`: adapter factories selected with --device.
- `ghostui_backend/service.py`: serialized device operations and confirmation.
- `ghostui_backend/adapters/marshall.py`: extracted legacy BLE transport/discovery.
- `ghostui_backend/adapters/demo_light.py`: simulated second-device example.
- `ghostui_backend/http_base.py`: browser routes, session token and validation.
- `ghostui_backend/server.py`: generation and paired mobile routes.
- `ghostui_backend/generation.py`: Gemini provider, environment loading and layout validation.
- `ghostui_backend/web/`: browser page and generation behavior as editable assets.
- `interface_generation.py`: compatibility re-export for previous imports.
- `ghostUI/`: existing Xcode project, kept in place to preserve signing and paths.
- `ghostUI/ghostUI/DeviceModels.swift`: transport capability models.
- `ghostUI/ghostUI/ContentView.swift`: pairing and capability-driven controls.
- `ghostUI/ghostUI/ARSceneView.swift`: camera, manual image-region registration and control-panel presentation.
- `marshall-acton3-ble/`: original diagnostics and standalone prototype, untouched.
- `tests/`: architecture and API compatibility checks without hardware or AI calls.

## Add a device

Implement the DeviceAdapter protocol, then register a factory in registry.py.
Each adapter supplies its own deviceId, name and controls; reads return a map of
control IDs to values. request((controlId, value)) sets a value and returns state.
discover() handles optional connection selection. close() releases resources.
The worker creates and uses adapters on one thread, preserving the BLE event loop.
Transport-specific discovery and connection fields belong inside the adapter.
Routes validate commands from the selected manifest; the browser and iPhone
render the same numeric capabilities. No HTTP or UI branches are needed per model.

The current contract supports integer numeric sliders only. Before adding RGB,
boolean or enumerated controls, extend the contract, validator and both renderers
together. Do not encode these as arbitrary numbers without documented semantics.

## Current scope

One selected device per running server, not a multi-device registry. The adapter
registry is a registry of implementations, not discovered physical objects.
Multiple simultaneous devices need instance IDs in routes and a UI device picker.
The iPhone uses capability-driven controls; Gemini-generated layouts currently
apply to the browser only. Camera object association is manual and session-scoped; Vision tracks the selected image region.
ObjectTracker.swift runs Vision on-device; ObjectSelectionOverlay.swift owns selection/highlight input.
Recognition, segmentation and persistent physical identity remain separate work.

## Compatibility and security

Default device is marshall. /state, /capabilities, /command, /generate and all
/mobile endpoints retain their shapes. LAN access stays opt-in with --lan and
phone bearer tokens still rotate on restart. The local browser uses its existing
session token and host checks. .env remains at project root, never served to clients.
No new external dependencies are required; the existing BLE virtualenv still works.

## Verify

Run `marshall-acton3-ble/.venv/bin/python -m unittest discover -s tests -v`.
Use `python app.py --simulate` for a speaker simulation, or
`python app.py --device demo-light` for the always-simulated light.
Rebuild the existing Xcode project for iPhone checks. Physical BLE and AR behavior
still require a real-device smoke test after the software checks pass.

## Local recognition integration

`recognition.py` owns YOLOE, reference persistence and the inference lock.
Authenticated `/mobile/vision` status and `/mobile/vision/{enroll,detect,clear}`
POST routes stay separate from device commands. The iPhone RecognitionClient
handles these routes; ObjectTracker combines periodic detections with Vision
tracking. A failure to detect never dispatches a device command. Configure model
inference device via GHOSTUI_VISION_DEVICE (CPU default; test MPS explicitly).
Images persist only during enrollment; live frames are processed in memory.
No Gemini image recognition is used. Multi-view enrollment and masks require
separate empirical validation; the present UI draws only detector boxes.

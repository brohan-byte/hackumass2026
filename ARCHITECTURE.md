# GhostUI architecture

GhostUI separates device connectivity from physical-object recognition and UI
interaction. The onboarding sequence is:

Choose integration → discover/pair → verify control → visually enroll → render UI.

## Project map

```
app.py                          Stable launch entry point
ghostui_backend/
  integrations/
    catalog.py                  Supported integration metadata and factories
    marshall.py                 Working Acton III BLE connection and controls
    demo_light.py               Explicitly simulated light integration
  onboarding/service.py         Connection verification and onboarding summary
  contracts.py                  Capability schema and command validation
  registry.py                   Existing factory API backed by the catalog
  service.py                    Serialized commands and readback confirmation
  recognition.py                YOLOE enrollment, saved views and segmentation
  generation.py                 Gemini layout generation and validation
  server.py                     Paired phone routes and generation routes
  http_base.py                  Browser routes and authentication
  web/                          Browser UI assets
  adapters/                     Compatibility imports for previous module paths
ghostUI/ghostUI/
  App/                          App entry and main connection/control screen
  Core/Models/                  Shared capability models
  Core/Networking/              Paired API transport and recognition client
  Features/Onboarding/          Typed onboarding client and response models
  Features/AR/                  Camera lifecycle and AR screen composition
  Features/Recognition/         Device highlight and on-device region tracking
  Features/Gestures/            Hand tracking, gesture state machine and sliders
  Assets.xcassets/               Existing assets
  NetworkInfo.plist             Existing permissions/configuration
tests/                          Backend, onboarding and gesture checks
tools/                          Developer setup utilities
marshall-acton3-ble/             Standalone diagnostic project; not app code
```

The Xcode project uses folder-backed source membership. Nested Swift sources are
included without changing the project identity, signing settings or plist path.
Root `.env`, `data/vision`, model paths and launch commands stay in place.

## Integration boundary

An integration describes a supported device family/protocol; a device instance
is one physical unit with a connection identity. `integrations/catalog.py` lists
only working implementations. WLED brightness is generated from a reviewed JSON API binding and tested against a
local HTTP fixture. Use the README generator instructions to repeat this with Gemini.
Matter and ESP32 provisioning remain future work.

Each implementation satisfies `DeviceAdapter`: capabilities, discover, request,
and close. Discovery and authentication belong inside the integration. The
single-threaded DeviceWorker owns the adapter's lifecycle, validates writes and
checks readback without repeatedly writing. UI and recognition contain no
Marshall-specific command logic.

Capabilities currently support integer numeric sliders only. Extend the schema,
validation, generated layout and renderers together before adding boolean, RGB,
or enum controls. Gesture HUD currently displays up to three controls.

## Onboarding boundary

`GET /mobile/onboarding` returns the catalog, selected integration and enrollment
summary. `POST /mobile/onboarding/verify` with `{}` validates a fresh read of all
capabilities. Both require the existing paired-phone authentication. Verification
is read-only and explicitly does not claim physical identity confirmation.

The iPhone connects to the Mac, loads the selected integration, verifies state,
and offers controls for a user-confirmed physical test. Opening AR loads saved
views and starts detection automatically; saving a new view resumes detection.
Visual enrollment is stored separately from the connection adapter.

This is the foundation for an Add device wizard. Selection currently occurs at
Mac startup with `--device`, not in the phone. There is one active device per
server. No multi-device switching, persistent onboarding completion, firmware
flashing or automatic reverse engineering is implemented by this reorganization.

## Recognition and identity

The recognition service persists enrollment images on the Mac under the adapter's
`deviceId`. YOLOE detects enrolled appearances and returns a box/mask. The phone
uses Vision tracking between detector responses. A detection never sends a command.
Existing IDs (`speaker-1`, `demo-light-1`) are preserved to keep saved enrollments.
They are demo IDs, not unique physical-device identifiers: before supporting two
speakers or lights, add a device-instance store and namespace enrollment by the
instance ID. Do not treat a matching appearance as authentication.

## Interaction and generation

The backend generates and validates layouts against capabilities. GET /mobile/layout
returns the cached AR layout or default controls. POST /mobile/layout with optional
boolean refresh generates when needed; both routes require paired-phone auth.
ARLayoutService persists successful Gemini layouts under data/ar-layouts using
a device and capability schema hash. Failed regeneration preserves a saved AI
layout, and invalid or missing cache entries fall back to explicit defaults.
The phone automatically prepares the layout after connection verification and supports
explicit regeneration. Responses carry deviceId, which the phone checks against
its connected capabilities before displaying a layout. Visual enrollment is scoped
to the same deviceId by RecognitionService, binding the detected object to its controls.
ControlLayout validates bindings, widget types and labels, then preserves trusted
ranges while resolving the generated order. The overlay renders the title, labels
and groups. The resulting ordered controls drive both gesture targets and drawing.
Hand tracking runs locally with Apple Vision, up to 20 Hz with cursor smoothing.
Three centered vertical sliders share rendering and hit-target geometry. Pinch
captures a thumb; drag previews a bounded value; release sends one absolute
command. Lost hands cancel. Object detection pauses in the HUD and resumes on Back.
Touch controls remain available. Camera frames go to the Mac for object detection;
hand inference stays on the phone and images are not sent to Gemini.

## Extension sequence

1. Verify the generated WLED brightness adapter against the physical ring using
   its local address and the existing onboarding/control/recognition flow.
2. Add persistent device instances, per-instance routes and a phone integration
   picker. Bind visual references to instance IDs, not adapter families.
3. Add ESP32 provisioning as a separate module: known hardware recipe, firmware
   template, compile, USB flash, network configuration and identity verification.
4. Add assisted adapter development from documented APIs. Review/test an adapter
   before adding it to the executable catalog; REA is a developer investigation tool.

## Verification

Run `.venv-vision/bin/python -m unittest discover -s tests -v`.
Run `python app.py --simulate` or `python app.py --device demo-light` for simulation.
The existing hardware launch remains `.venv-vision/bin/python app.py --lan`.
Rebuild in Xcode after the source moves. Software checks do not replace a physical
BLE/reconnection, recognition and gesture smoke test on the iPhone.

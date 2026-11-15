# GhostUI architecture

GhostUI separates device connectivity from physical-object recognition and UI
interaction. The onboarding sequence is:

Discover/select a named device → prepare/verify connection and UI → test control
→ visually enroll → recognize and control. Protocol choices stay on the backend.

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
  devices.py                    Persistent instance registry and runtime selection
  service.py                    Serialized commands and readback confirmation
  recognition.py                YOLOE enrollment, saved views and segmentation
  scene.py                      Shared visual prompt bank for all enrolled objects
  onboarding/registration.py    Names-only choices and Home Assistant entity import
  onboarding/documented.py      URL-to-mapping onboarding and live verification
  onboarding/discovery.py       Read-only WLED mDNS discovery and unit identification
  onboarding/setup.py           Phone setup jobs, adapter generation and layout preparation
  integrations/documented_http.py Data-driven HTTP adapter runtime
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

The phone first pairs with the Mac and calls `GET /mobile/devices` internally. This works
with an empty registry. `POST /mobile/devices` accepts `integrationId`, optional
`address`, `name` and `simulated`; registration connects, verifies readable state,
then atomically saves the instance. `POST /mobile/devices/<id>/select` with `{}`
switches to a saved instance. Both mutations return the refreshed list.

`DeviceManager` stores records in ignored `data/devices.json`. Records include a
unique instance ID, integration, connection address, adapter-reported identity,
capabilities and enrollment association. Home Assistant identity includes its
configured server URL so equally named entities on different servers do not merge.
No API, pairing or Home Assistant token is stored in the registry.

One device session is active per backend. A session owns a serialized DeviceWorker,
recognition service, AR layout service and browser tokens. A lock keeps that
session alive until each request completes; selection waits for in-flight work.
New selection is installed only after connection verification and successful
persistence. Failed connections retain saved records and the previous active
session. Selecting a saved address checks the reported identity before adoption.
WLED identity is its reported MAC; Marshall relies on its Mac BLE peripheral address.
Neither is cryptographic authentication.

All phone operations use `/mobile/devices/<id>/` followed by `capabilities`,
`state`, `command`, `onboarding`, `onboarding/verify`, `layout`, `vision`, or
`vision/enroll|detect|clear`. The native client inserts the captured device ID.
Unknown IDs return 404 and requests targeting an inactive saved device return 409.
Unscoped phone operations are rejected in registry mode to avoid stale clients
acting on a newly selected device. The legacy single-worker handler remains
available to compatibility callers/tests. Browser command and generation tokens
rotate on selection, invalidating old browser controls.

Verification is read-only. Registration shows only real device names from
`GET /mobile/registration`. Its choices combine saved direct connections with
supported entities from a configured Home Assistant server. `POST` to the same
route with `deviceId` resolves the choice entirely on the backend and returns
the saved instance ID. Home Assistant URL, entity IDs and credentials never become
phone form fields. Failed hub queries preserve direct-device choices.

The phone asks the user to test a control and confirm the physical target, then
opens the existing boxed-view enrollment camera. Normal use is the camera itself,
without a saved-device picker. Selecting an identified outline automatically
activates the corresponding backend connection, verifies state and loads its
Gemini layout. Settings contain the temporary Mac bridge connection only.

## Phone-driven WLED setup

Paired, native-only routes:

- `POST /mobile/setup/discover {}` returns opaque candidate IDs and names. The
  Mac browses `_wled._tcp.local.`, resolves local IPv4 addresses and checks
  `/json/info` for WLED identity and a unit MAC. Advertisements do not supply
  executable code, API URLs or command templates.
- `POST /mobile/setup/start {"candidateId":"..."}` starts a background setup job.
  A server-owned family rule supplies the official documentation URL. The job
  uses `DocumentedOnboarding` and Gemini for a new mapping, verifies the selected
  MAC against the actual adapter identity response before saving, then resolves
  the AR layout. Saved generated connections reuse their mapping and cache.
- `GET /mobile/setup/jobs/<id>` reports progress, failure or the resulting saved
  instance ID. One setup job runs at a time; duplicate in-flight starts for the
  same candidate return the same job, avoiding duplicate generation calls.

Candidates expire after five minutes; scanning, candidates and jobs are bounded.
Failures do not select a bundled adapter or actuate hardware. The phone opens
the existing control-confirmation and visual-registration flow after setup.
New setup is WLED-only; firmware/Wi-Fi provisioning and general API web search
remain outside this feature. Multicast discovery requires a suitable LAN.

## Generated HTTP mappings

`--onboard ADDRESS --api-docs HTTPS_URL` downloads bounded visible documentation
text and calls the existing Gemini mapping extractor. Schema/path/range validation
precedes device requests. A `DocumentedHttpAdapter` is created on the normal device
worker thread using the validated JSON mapping; no downloaded Python is executed.
Identity and numeric state must pass before the record is saved. Automatic setup
performs no device writes. Physical confirmation and command readback use the
existing phone registration/control flow.

The record's `integrationId` is `generated-http`; `adapterBinding` stores executable
runtime data and `adapterProvenance` stores source URL, hashes, model, timestamp
and read-only verification scope. Reconnection restores the saved mapping without
fetching docs or regenerating. Instance identity uses the documented vendor and
unique unit ID, independent of Gemini's chosen family label. Gemini AR layout
creation and visual enrollment remain keyed to the resulting saved instance.

An explicit generation failure stops startup instead of selecting a built-in
adapter. The CLI reserves its listening port first to avoid generating into a
registry while an old server still occupies the port. This feature supports the
existing single percentage-control HTTP contract only. Documentation discovery,
authenticated/nested APIs and BLE generation require additional work.

## Recognition and identity

New enrollment uses per-instance storage. First registration of the original real
Marshall or WLED reuses its old enrollment key; validated Gemini layouts are
copied to the new instance/capability cache. Original files are preserved. A second
Marshall cannot claim the first speaker's legacy views. Register the original
speaker first because the old `speaker-1` key did not encode physical identity.
Simulations cannot claim real-device legacy references.

A detection proposes a match to a saved instance. It does not establish a new
network endpoint or authenticate physical identity. The phone uses YOLOE masks and local Vision
tracking as before. The shared `SceneRecognitionService` builds a mosaic from all real-device views,
with a prompt-class-to-device-ID mapping. `/mobile/scene/vision` reports status;
`POST /mobile/scene/vision/detect` accepts one image and returns boxes/masks with
`deviceId` and name. Scene recognition does not select an adapter or send commands.
The shared model is invalidated when reference views change. Duplicate views of
one object are merged, while overlapping identities or multiple physical copies
of the same enrolled device are suppressed rather than assigned arbitrarily.

The phone independently tracks each identified box between detections and renders
an outline for each. Touch/pinch selection carries its device ID. The selected
control session is still singular; multiple physical objects can be recognized
and selected from the same camera session. Simulations remain backend developer
fixtures and are excluded from names-only registration and scene recognition.

## Interaction and generation

The backend generates and validates layouts against capabilities. GET /mobile/devices/<id>/layout
returns the cached AR layout or default controls. POST /mobile/devices/<id>/layout with optional
boolean refresh generates when needed; both routes require paired-phone auth.
ARLayoutService persists successful Gemini layouts under data/ar-layouts using
a device and capability schema hash. Failed regeneration preserves a saved AI
layout, and invalid or missing cache entries fall back to explicit defaults.
The phone automatically prepares the layout after connection verification automatically. Responses carry deviceId, which the phone checks against
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

1. Camera-first registration and shared recognition are implemented; validate switching Marshall/WLED
   on physical hardware and keep the known manual launch as a comparison.
2. Add QR server pairing and discovery for known protocols, with explicit
   selection, identity checks and physical confirmation before visual enrollment.
3. Home Assistant entity names are available during registration; extend supported capability types as needed.
4. Add documented-API adapter proposals as a separate review/test workflow;
   select known adapters first and never execute unreviewed generated code.
5. Treat ESP32 firmware provisioning as a separate future module.

## Verification

Run `.venv-vision/bin/python -m unittest discover -s tests -v`.
Run `python app.py --simulate` or `python app.py --device demo-light` for simulation.
Use `.venv-vision/bin/python app.py --lan` to restore the last device or start
empty; `--device marshall --lan` explicitly registers/selects the speaker.
Rebuild in Xcode after the source moves. Software checks do not replace a physical
BLE/reconnection, recognition and gesture smoke test on the iPhone.

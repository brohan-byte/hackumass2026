# GhostUI

A capability-driven device-control prototype with Gemini-generated native AR
controls, visual enrollment, hand gestures and saved device connections.

## New contributors

Read [the project onboarding guide](docs/ONBOARDING.md) for current progress,
the planned device setup experience, code ownership, and the next milestones.

## Add a WLED light from the phone

The Mac backend still runs for the hackathon, but adding a WLED light no longer
requires a device address, documentation URL or generation command. Rebuild the
iPhone app for the new flow. For a fresh registration demo, start the server with:

```sh
.venv-vision/bin/python app.py --data-dir data/phone-setup-demo --port 8783 --lan
```

Connect the phone using the printed URL/token, then tap **Register object**.
An empty registry searches automatically; otherwise tap **Find new device**.
Select the discovered light by name (a default controller may be named **WLED**).
The app shows setup progress, generates and verifies the connection, creates the
Gemini AR controls, and opens the test slider. Confirm the light, save boxed
views, then return to detection and pinch controls. Reuse the same command/data
directory on later starts; saved connections and layouts are reused.

Discovery uses WLED's `_wled._tcp.local.` mDNS advertisement and a read-only
`/json/info` identity check. The detected WLED family selects the official API
documentation URL, then calls the same Gemini mapping pipeline as `--onboard`.
No prebuilt WLED adapter is substituted if generation fails. Existing saved WLED
connections can be reused. The phone receives candidate IDs/names only, without
addresses or protocol settings. Setup checks the unit identity again before
saving, and does not change brightness until the user tests a control.

WLED must already have firmware and Wi-Fi configured. The Mac needs internet for
new Gemini calls, and the network must allow local device traffic and mDNS.
Discovery currently supports WLED; arbitrary device/API search and Wi-Fi
provisioning are not implemented. If no light appears, check the shared Wi-Fi
and retry. Do not reflash an already working light for this flow.

## Documentation-driven adapter onboarding (developer CLI)

The backend can fetch a supplied HTTPS API documentation page, ask Gemini for a
bounded JSON mapping, verify live identity/state and save the connection. Each
saved record contains the mapping, source URL, documentation/mapping SHA-256 and
Gemini model. It uses the fixed `DocumentedHttpAdapter` transport at runtime,
without importing generated Python or editing a catalog for each new binding.

For the working light, replace the address if it changes:

```sh
.venv-vision/bin/python app.py --onboard 10.0.0.152 \
  --api-docs https://kno.wled.ge/interfaces/json-api/ \
  --name "Ring light" --data-dir data/onboarding-demo --port 8781 --lan
```

This isolated registry leaves the existing Marshall/WLED demo on port 8780 intact.
In the phone's connection settings, enter the Mac's printed address with port
8781 and its new pairing token. Tap **Register object → Ring light**, test the
brightness slider, confirm the device and save views. Gemini generates/caches the
AR layout from the newly created adapter capabilities through the existing flow.

After successful generation, restart without fetching documentation or calling
Gemini for the adapter again:

```sh
.venv-vision/bin/python app.py --data-dir data/onboarding-demo --port 8781 --lan
```

`--onboard` explicitly requests generation; it does not silently select the bundled
WLED adapter on failure. Bad/unsupported mappings or failed device verification
stop onboarding and preserve existing records. Startup checks the port before
spending an API call. Onboarding itself reads only: the phone's test slider verifies
a write and physical association. Use a new `--data-dir` for a completely fresh
registration demo; keep the original data as a fallback.

Current scope is one integer percentage control on flat, unauthenticated HTTP(S)
JSON endpoints. The API must document a unique unit identifier, name, matching
vendor field, readable state and a JSON POST control. This automates the path from
a supplied documentation URL; online API search, arbitrary BLE protocol inference,
authentication generation and universal device compatibility are not implemented.
The legacy `adaptergen --docs ... --output ...` developer tool remains available.

## Camera experience (current version)

For the Sony XM5 deadline demo, see [Mac playback setup](docs/SONY_XM5.md).
It uses the same registration/Gemini AR/gesture flow, with an explicitly labeled
Mac playback volume control. Private Sony settings remain experimental.

The phone opens a camera with **Register object** and a small connection-settings
button. During registration it shows real device names only. The user chooses
which physical device to link, tests a control to confirm it, and draws boxed
views from up to four angles. Returning to the camera searches all enrolled real
objects together. Tap or pinch an outline to open that object's generated controls.

The phone has no integration picker, simulation switch, saved-device manager,
IP field, or Home Assistant device type. Device records, addresses and adapter
selection stay on the Mac. Connection settings temporarily retain the Mac server
address/pairing code required by the hackathon bridge.

The camera keeps a recent object target briefly through tracking loss. When a
hand appears or a touch begins, it freezes the known target for up to three
seconds so covering a small light does not remove its controls button. Moving the
camera significantly invalidates that retained position. The outline and its
label both open controls; object detection stays paused while the controls are open.

### Configure test devices on the Mac

Stop the current server with Ctrl-C before launching another on the same port.
First configure the original Marshall to preserve its legacy enrollment:

```sh
.venv-vision/bin/python app.py --device marshall --lan
```

After it connects, stop it and configure WLED using the controller's current IP:

```sh
.venv-vision/bin/python app.py --device wled 192.168.1.42 --name "Ring light" --lan
```

Both connections remain in ignored `data/devices.json`. Future starts can use:

```sh
.venv-vision/bin/python app.py --lan
```

Rebuild the iPhone app, connect through the settings button using the newly
printed URL/token, tap **Register object**, and choose the physical device by
name. Test the slider, tap **That's my device · Continue**, save views, then tap
**Done**. Repeat for the other device. Both objects can then be highlighted in
the same camera session; tap/pinch the desired outline for its controls. The first
combined-model inference may need time to warm up. Test recognition on real
objects under demo conditions before presenting.

Stored layouts and views survive restarts. The first real Marshall registration
claims the legacy speaker views; verify it is the original speaker. WLED legacy
views are matched by reported identity. Simulated connections are developer-only
and are excluded from the phone's registration list and camera recognition.

### Home Assistant's role

Home Assistant is an optional central hub. When a real Home Assistant server is
configured with `HOMEASSISTANT_URL` and `HOMEASSISTANT_TOKEN` in Mac `.env`, its
supported lights, speakers and fans appear by friendly name during registration.
The backend translates their controls through Home Assistant. A user chooses
“Desk lamp,” never “Home Assistant.” Installing/running a real Home Assistant
server is separate from the included REST adapter and local fixture server.

Direct Marshall BLE and WLED HTTP paths remain available for the existing demo.
They use the same internal capability contract. WLED Wi-Fi discovery and
phone-driven mapping generation are available; broader protocol discovery and
arbitrary adapter generation remain later work. The Mac currently keeps one
control connection open and switches it automatically when an object is chosen;
shared visual recognition searches all registered real objects independently.

## Run the existing Marshall experience

From this folder:

```sh
.venv-vision/bin/python app.py --device marshall --lan
```

Close other speaker-control scripts and the Marshall app first. Without an
address, startup scans for a compatible Acton III and validates its legacy BLE
controls. An optional explicit BLE address still works. The extracted wire
implementation preserves the prior prototype's connection and read/write logic.

- Browser: http://127.0.0.1:8780
- iPhone: use the printed Phone server address and pairing token.
- Both devices must use the same trusted Wi-Fi; allow local-network access.
- The phone token changes on restart. LAN access is opt-in and uses HTTP, suitable
  for a trusted local demo, not internet deployment.
- Open `ghostUI/ghostUI.xcodeproj` in Xcode and rebuild for iPhone changes.

## Generate a Wi-Fi adapter

From the project root, give the generator plain-text API notes. It sends the notes
and the supported GhostUI adapter contract to Gemini using the existing server
key. It validates the returned mapping and emits a Python adapter using the HTTP
transport in `ghostui_backend/integrations/http_level.py`. Generation runs on
the Mac and writes a new file. Inspect its endpoints, identity check, fields
and numeric range before adding a new family to the integration catalog.

```sh
.venv-vision/bin/python -m ghostui_backend.adaptergen --docs examples/adaptergen/wled-api.md --output /tmp/wled_candidate.py
diff -u ghostui_backend/integrations/wled.py /tmp/wled_candidate.py
```

To reproduce the bundled WLED adapter offline, use
`--binding examples/adaptergen/wled.json` in place of the `--docs` argument.
Use a fresh output filename each time. The generator covers one integer 0–100
control on an unauthenticated HTTP(S) JSON device, flat identity and state objects,
a JSON POST, and linear scaling with optional on/off state. Other protocols
and control types need additional runtime support.

Once the ring is reachable, substitute its address and run:

```sh
.venv-vision/bin/python app.py --device wled 192.168.1.42 --lan
```

Connect the iPhone with the printed URL and token. Tap Register object, choose the light, set brightness to 40% and
check that the ring responds and the app confirms 40. Zero turns the ring off.
The generated adapter identifies the controller by its reported MAC address.

## No-hardware checks

```sh
marshall-acton3-ble/.venv/bin/python app.py --simulate
marshall-acton3-ble/.venv/bin/python app.py --device demo-light --lan
marshall-acton3-ble/.venv/bin/python -m unittest discover -s tests -v
```

`demo-light` is always simulated. It exposes brightness and warmth to the developer
browser/API and does not connect to an ESP32 or real light. The phone hides these
simulations from its real-device registration and recognition experience.

## Gemini

Export GEMINI_API_KEY before starting the server, or copy `.env.example` to
`.env` in this root folder and set the key locally. Never commit or share the
actual file. An optional GEMINI_MODEL overrides the default model; check model
availability and quota in Google AI Studio. No extra AI SDK is required.

Only capability metadata and the style preference are sent for generation.
The model selects title, order, labels and groups. Adapter capabilities retain
control IDs and valid ranges. Invalid layouts or unavailable API access produce
a visibly labeled template fallback. The iPhone automatically requests a Gemini AR layout after connecting to a device and renders the
validated title, labels, groups and order with native vertical sliders. Generation runs automatically after connection. Successful layouts
are cached per device and capability schema on the Mac in data/ar-layouts, allowing
reuse without internet. The Mac needs internet for a new Gemini call; WLED-AP alone
provides local control only. Offline generation uses clearly labelled default controls.
Slider ranges and bindings always come from the adapter. The gesture HUD currently
shows up to three controls. Restart the backend and rebuild the iPhone app for this update.

## Organization

See [ARCHITECTURE.md](ARCHITECTURE.md) for the extension contract and module map.

```text
app.py                         stable launcher
interface_generation.py        compatibility imports
ghostui_backend/
  cli.py                       startup and LAN pairing
  contracts.py                 adapter contract and capability validation
  registry.py                  adapter factories
  devices.py                   persistent device instances and runtime selection
  scene.py                     all-object recognition and identity disambiguation
  service.py                   serial commands and readback confirmation
  integrations/                catalog, Marshall BLE and simulated light
  onboarding/                  connection verification and enrollment summary
  adapters/                    compatibility imports
  generation.py                Gemini generation and validation
  http_base.py, server.py      browser and iPhone routes
  web/                         browser HTML and generation JavaScript
ghostUI/                       existing Xcode project
  ghostUI/App/                 app shell and connection/control screen
  ghostUI/Core/                models and shared paired API transport
  ghostUI/Features/             onboarding, AR, recognition and gestures
marshall-acton3-ble/            original standalone driver/diagnostics
tests/                         compatibility and architecture checks
```

The main app no longer imports the standalone Marshall demo. That folder remains
unchanged and supplies the existing virtualenv used in these run commands.
New device families implement the adapter contract in `integrations/` and add a
catalog entry in `integrations/catalog.py`. The iPhone loads onboarding metadata
and verifies readable state; the user still confirms which physical device responds. Current
renderers support integer numeric sliders; other control types require shared
contract and renderer changes. One control session is open at a time; camera recognition searches all enrolled real devices.

## YOLOE enrollment and detection

The recommended local vision environment is now `.venv-vision` (Python 3.13).
It includes BLE and YOLOE/PyTorch, while the original BLE environment is untouched.
Weights are in `models/yoloe-26s-seg.pt`; a prepared installation can start with:

```sh
.venv-vision/bin/python app.py --lan
```

Rebuild the existing Xcode project on your iPhone, connect using the printed
address/token, then choose **Open camera · Select object**.

1. Drag a tight box around the object below the instruction panel. The image freezes
   when drawing begins, and lifting your finger submits the view automatically.
2. Wait for “Saved view 1/4.” Use **Add view** and draw from another angle.
   If saving fails, the error stays visible with **Retry saving** and **Redraw** actions.
3. Add right-side and different-distance views, up to four total.
4. Detection starts automatically after drawing a valid box. The initial model warm-up can take tens of seconds;
   later calls reuse the model and visual prompts.
5. Hold reasonably steady during detection. A matching box becomes highlighted;
   tap it to open controls. iPhone Vision tracks between periodic Mac detections.
6. Point away, return and hold steady to test reacquisition. **Add view** extends
   enrollment; **Clear** deletes the selected device's saved reference views.

The phone sends reduced JPEG snapshots to the paired Mac, not to Gemini or any
other cloud inference service. Boxed reference images/metadata persist under
`data/vision/`, separated by device ID. Live detection frames are not written to
disk. `data/`, `models/`, and `.venv-vision/` are ignored by Git. Closing/reopening
the camera preserves Mac enrollment; reconnecting after server restart still
requires the new pairing token. Opening AR automatically starts detection with saved views.

YOLOE's visual-prompt mode uses a mosaic of up to four object-centered crops with a separate visual
prompt ID for each view; all IDs map to the selected device. This conditions an existing detector; it does not train a new model.
Only one request runs at a time and the phone waits three seconds between
completed detector calls. Local tracking updates at up to ten Hz. Old detections
are rejected if the phone moved significantly or the result is over twelve
seconds old. Ambiguous multiple detections hide the active highlight rather than
choosing a random object. Controls do not open or execute actions automatically.

This version uses silhouette masks when available, with bounding-box fallback. The model can
confuse similar objects, miss unseen angles, or drift during local tracking.
Recognition does not authenticate physical BLE identity. Test enrollment on the
actual speaker before relying on it. Camera orientation, camera image cropping,
network speed and heat/load on the Mac affect results.

## Reinstall vision dependencies

```sh
/opt/homebrew/bin/python3.13 -m venv .venv-vision
.venv-vision/bin/python -m pip install -r requirements-vision.txt
.venv-vision/bin/python tools/setup_vision.py
.venv-vision/bin/python -m unittest discover -s tests -v
```

The setup script downloads official Ultralytics weights. Check the upstream
[YOLOE documentation](https://docs.ultralytics.com/models/yoloe/) for visual
prompts and project licensing. No dataset or speaker images are uploaded during
setup. The Gemini layout generator remains independent of recognition.

## Verification

Backend checks include registry persistence, selection isolation, enrollment migration,
Home Assistant, layout validation and existing control/recognition routes. Real visual-prompt inference and prompt reuse
were exercised using a synthetic test image: roughly 17 s cold and 365 ms warm
in that run. These are smoke-test timings, not benchmark guarantees or measured
speaker recognition accuracy. The iPhone code type-checks against the iOS SDK.
Real speaker accuracy, camera alignment, end-to-end latency and usability still
need on-device testing.

## Segmentation and gesture controls

YOLOE returns simplified mask polygons for a mint speaker silhouette, with a box
fallback. Between detections the phone transforms the polygon with its local
bounding-box tracker; this approximates the silhouette between model results.

Rebuild and run the iPhone app, keeping the paired Mac backend running:

1. Open AR. Detection starts automatically when saved speaker views and the detector are available.
   For a new device, draw a box to save an enrollment view; detection starts automatically. Use Add view for additional angles.
2. Show one hand to the rear camera. The index fingertip controls the cursor.
3. Point the cursor inside the highlighted speaker, pinch thumb/index for at
   least 0.25 seconds, then release to open the gesture HUD.
4. Point at a Volume, Bass, or Treble slider thumb and pinch to grab it.
5. Drag up/down while pinching; the thumb and value preview follow the drag.
   Release to apply the absolute value. Up increases; down decreases.
6. Pinch/release over Back to resume speaker search, or Close to leave AR.
   Use touch sliders remains available as a fallback.

Open your hand before each gesture. Cyan dots show hand landmarks; the cursor
highlights a target and turns green after a sufficiently long pinch. Grabbing
a thumb does not send a device command. Previews remain local until release;
the app sends an absolute value clamped to the device capability range.
Only one command can run at a time, with confirmation/error feedback in the HUD.

Object detection pauses while the HUD is open, so the speaker need not stay in
view and a hand covering it does not disrupt selection. Returning to search
requires a fresh detection. Lost, uncertain, or multiple hands cancel a pending
gesture. Orientation changes, backgrounding, and leaving AR cancel it too.
Apple Vision performs hand tracking locally; no MediaPipe download is required.

The gesture state-machine tests cover arming, release debounce, short-pinch
rejection, hand-loss cancellation, timeout, target capture, and vertical slider range clamping.
Hand sampling is capped at 20 Hz with cursor smoothing and pinch hysteresis.
Actual camera visibility and gesture comfort still require testing on the phone.

# GhostUI

A capability-driven device-control prototype with a Gemini-generated browser
layout and an iPhone app for manual AR placement and controls.

## Run the existing Marshall experience

From this folder:

```sh
marshall-acton3-ble/.venv/bin/python app.py --lan
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

## No-hardware checks

```sh
marshall-acton3-ble/.venv/bin/python app.py --simulate
marshall-acton3-ble/.venv/bin/python app.py --device demo-light --lan
marshall-acton3-ble/.venv/bin/python -m unittest discover -s tests -v
```

`demo-light` is always simulated. It exposes brightness and warmth to the same
routes/renderers used for Marshall; it does not connect to an ESP32 or real light.

## Gemini

Export GEMINI_API_KEY before starting the server, or copy `.env.example` to
`.env` in this root folder and set the key locally. Never commit or share the
actual file. An optional GEMINI_MODEL overrides the default model; check model
availability and quota in Google AI Studio. No extra AI SDK is required.

Only capability metadata and the style preference are sent for generation.
The model selects title, order, labels and groups. Adapter capabilities retain
control IDs and valid ranges. Invalid layouts or unavailable API access produce
a visibly labeled template fallback. The iPhone currently renders capabilities
directly; the generated layout applies to the browser.

## Organization

See [ARCHITECTURE.md](ARCHITECTURE.md) for the extension contract and module map.

```text
app.py                         stable launcher
interface_generation.py        compatibility imports
ghostui_backend/
  cli.py                       startup and LAN pairing
  contracts.py                 adapter contract and capability validation
  registry.py                  adapter factories
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
contract and renderer changes. One selected device runs per server instance.

## YOLOE enrollment and detection

The recommended local vision environment is now `.venv-vision` (Python 3.13).
It includes BLE and YOLOE/PyTorch, while the original BLE environment is untouched.
Weights are in `models/yoloe-26s-seg.pt`; a prepared installation can start with:

```sh
.venv-vision/bin/python app.py --lan
```

Rebuild the existing Xcode project on your iPhone, connect using the printed
address/token, then choose **Open camera · Select object**.

1. Drag a tight box around the front of the speaker, below the instruction panel.
   A yellow preview remains. Tap **Save view** to submit it; drawing alone does not enroll.
2. Wait for “Saved view 1/4.” Move to the left side and draw another box.
3. Add right-side and different-distance views, up to four total.
4. Detection starts automatically after saving a view. The initial model warm-up can take tens of seconds;
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

This version uses bounding-box highlights, not silhouette masks. The model can
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

20 unit/compatibility tests pass. Real visual-prompt inference and prompt reuse
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
   For a new device, save an enrollment view; detection starts automatically. Use Add view for additional angles.
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

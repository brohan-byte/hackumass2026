# GhostUI project onboarding

Contributor guide • updated 15 November 2026

## Current update: camera-first experience

WLED can now be added directly from the phone: **Register object → Find new
device → light name** (an empty registry searches automatically). The Mac
discovers WLED over mDNS, identifies the unit, selects its official API reference,
calls Gemini for a mapping, verifies identity/state and generates the AR layout.
The phone then opens the existing slider confirmation and boxed-view enrollment.
Device-specific terminal commands and IP/documentation entry are no longer
required for this WLED flow. See the README for a fresh-profile demo command.
Firmware installation and joining Wi-Fi are still prerequisites. The Mac remains
the hackathon bridge. Broader device discovery/API identification is future work.

The phone opens directly to the camera. A settings icon holds the temporary Mac
address/pairing code. **Register object** shows real device names only, asks the
user to test a control and confirm the physical target, then opens boxed-view
registration. Saved devices, addresses, protocol choices and simulation live on
the backend. There is no phone saved-device manager or integration picker.

The backend now searches all enrolled real objects using one YOLOE visual prompt
bank. Detections carry a device ID and name; the phone tracks and outlines each
match independently. Tapping or pinching an outline automatically opens that
object's controls. One control connection remains active internally, with automatic
switching on object selection. This is separate from recognizing several objects
in one camera image. Physical multi-object accuracy/latency still needs validation.

Configure direct test connections on the Mac with the existing `--device` launches
(one server process at a time); records accumulate in `data/devices.json`. Start
future sessions with `.venv-vision/bin/python app.py --lan`. A configured Home
Assistant server supplies additional friendly device names during registration;
Home Assistant itself is never presented as a device type. Its REST adapter is
not a bundled Home Assistant server. Simulation is a developer-only fake device
state and is hidden from the real-device camera flow.

See [README.md](../README.md) for the current test flow and
[ARCHITECTURE.md](../ARCHITECTURE.md) for APIs. The remainder below records the
earlier roadmap; startup-only selection and phone device-picker descriptions are
historical and superseded by this update.

GhostUI turns a supported physical device into an interactive camera interface.
The user looks at a registered object, sees a highlight, opens its controls, and
changes real settings through touch or hand gestures. The project already has a
working Marshall Acton III demonstration. The generated WLED brightness adapter has passed a local HTTP fixture test. The next
objective is to verify it with an ESP32 and NeoPixel ring. See the README for generation and launch commands.

This guide explains the current implementation, the intended user experience,
and the engineering work required to connect them. **Firmware provisioning,
discovery beyond WLED, and a general Add device wizard are planned,
not implemented.** WLED discovery/setup is implemented as described above.

## Where the project stands

| Area | Current state | Important boundary |
| --- | --- | --- |
| Real device control | Marshall Acton III volume, bass and treble work through the Mac BLE adapter | Verified with the owner's speaker; firmware compatibility is not universal |
| Phone connectivity | Native iPhone app connects to a paired Mac backend over LAN | Mac is still required for this demonstration |
| Recognition | User enrolls boxed views; Mac YOLOE detects the object; phone Vision tracks between detections | Appearance matching does not authenticate the physical device |
| Highlight | Detector mask outline with a bounding-box fallback | Between detections, contour movement is approximated from the tracked box |
| AR startup | Opening AR loads saved views and starts detection automatically | Missing enrollment requires the user to save a view first |
| Interaction | Pinch to select the highlighted device, then operate three centered vertical gesture sliders | Touch controls remain available; gesture HUD shows at most three controls |
| Interface generation | Gemini generates a browser layout validated against adapter capabilities | Native AR now renders validated Gemini title, labels, groups and order with shared native sliders |
| Extensibility | Integration catalog, adapter contract, onboarding summary and read-only connection verification exist | One active device per server, selected at Mac startup |
| Light example | Demo light exercises the shared pipeline in simulation | It does not control the ESP32 or NeoPixel ring |
| Hardware available | ESP32 and NeoPixel ring | Board model, ring type/count, power and wiring still need confirmation |

The last development checks passed: 24 backend tests, gesture state-machine tests,
and an iPhone Swift typecheck. These checks do not establish real-device reliability
for every reconnection, camera condition or hardware configuration.

## Understand the three identities

**Integration identity** identifies the protocol implementation, such as
`marshall`, `wled`, or a future GhostUI firmware protocol. One integration
can support many compatible physical units.

**Device instance identity** identifies one physical unit, together with its
connection details and credentials. Two identical lights must be distinct instances.
Current `speaker-1` and `demo-light-1` IDs are demo identifiers; they must be replaced
or migrated before simultaneous multi-device support is added.

**Visual enrollment identity** links saved object views to the verified device
instance. A camera match selects that instance's existing connection. It does not
create an API or discover which network endpoint belongs to a similar-looking object.

Do not bind a visual match to whichever device happens to be available. The user
must confirm the physical association during registration, especially when two
objects look identical.

## Run the current demonstration

Work from the `hackumass` project root. Keep the standalone `marshall-acton3-ble`
folder for diagnostics; production app changes belong in `ghostui_backend` and
`ghostUI`.

1. Close competing Marshall control scripts and the Marshall phone app.
2. Start the Mac backend with the vision environment:

   ```sh
   .venv-vision/bin/python app.py --lan
   ```

3. Open `ghostUI/ghostUI.xcodeproj` in Xcode and run on the iPhone.
4. Connect the phone using the server address and pairing token printed by the Mac.
   Both devices must share the trusted local network. The token changes on restart.
5. Test a touch control to confirm that the intended speaker changes.
6. Open AR. Saved views start recognition automatically. For new enrollment, draw
   a box and lift your finger to save the view, and use Add view for more angles, up to four.
7. Point the finger cursor inside the speaker highlight, pinch briefly and release
   to open the HUD. Pinch a slider thumb, drag up to increase or down to decrease,
   and release to apply. The value previews locally before release.

The rear camera must see the hand clearly. Object detection pauses in the gesture
HUD, so the speaker does not need to remain visible while adjusting it. Back resumes
object search. Losing the hand cancels the pending gesture.

For a hardware-free control demonstration:

```sh
.venv-vision/bin/python app.py --device demo-light --lan
```

`demo-light` is explicitly simulated. Gemini uses `GEMINI_API_KEY` from the server
process environment or root `.env`; keys are never entered into the phone or sent
to a device. Object camera frames are processed on the Mac, not sent to Gemini.

## Current end to end architecture

```text
Native iPhone
  camera → visual detection request → Mac YOLOE → object box or mask
  local Vision tracking → highlight → pinch selection → gesture HUD
  gesture release or touch → capability ID and absolute numeric value
                                      ↓
Mac backend over authenticated LAN HTTP
  capability validation → serialized worker → selected integration adapter
                                      ↓
Device transport
  Marshall BLE today     Wi-Fi light API planned
                                      ↓
Physical device → reported state → backend confirmation → phone feedback
```

The model can propose layout choices, labels and ordering. Trusted capability
metadata defines which controls exist and their valid values. The model does not
invent endpoints, BLE registers, arbitrary commands or firmware during normal use.

## Planned registration experience

The target flow is **choose integration → discover or provision → verify control →
visually enroll → show controls**. The current phone connection screen is the
foundation, not the completed registration wizard.

### Choose a supported device path

The user selects a supported integration or hardware recipe and supplies the
required details. A name such as Acton III helps select an adapter but is not
sufficient to infer a communication protocol or wiring.

Registration should offer two explicit paths:

- **Connect an existing supported device:** use its existing firmware and protocol,
  such as a supported commercial device or a controller already running WLED.
- **Set up a programmable board:** configure a tested ESP32 light recipe and install
  compatible firmware through the Mac.

Unsupported devices should be identified clearly. Do not present speculative
protocol guesses as a successful connection.

### Search for the device

Discovery must be implemented separately for each transport; the app cannot use
one generic scan to identify and control every device.

| Path | Proposed search and validation | User fallback |
| --- | --- | --- |
| Marshall BLE | Existing scan filters candidate advertisements and probes model and expected characteristics | Enter an explicitly scanned BLE address |
| Existing Wi-Fi light | Discover advertised services where supported, or accept its address; query an identifying API and validate its response | Enter IP or hostname |
| GhostUI firmware | Discover an advertised versioned GhostUI service; read a unique device ID and capability manifest | Enter hostname or IP |
| Blank ESP32 | Mac enumerates USB serial ports; user selects the connected board | Check cable, board driver and boot mode |

A blank ESP32 must not be assumed to advertise a useful Bluetooth or Wi-Fi setup
service. Wireless provisioning is possible only after firmware providing that
service exists. BLE advertisement names and network addresses are hints; protocol
validation and user confirmation establish which device is being registered.

For the first light integration, manual IP entry is an acceptable discovery
fallback. Automatic discovery can follow once reliable API control is established.

### Set up firmware for the ESP32 light

Firmware setup is a proposed new subsystem. The first supported recipe should use
one specified ESP32 board and NeoPixel ring configuration.

The setup form needs the exact board, LED chipset or ring type, RGB/RGBW format,
LED count, GPIO data pin, and network configuration. Confirm power and logic-level
requirements for that hardware before flashing. The user should review these
settings; visual recognition cannot establish the wiring.

The Mac provisioning service would:

1. Validate those details against a supported hardware recipe.
2. Fill configuration into a tested firmware template and compile for the board,
   or select a pinned compatible firmware image with a configuration mechanism.
3. Show the selected board and serial port and request approval before flashing;
   flashing replaces the firmware already on the board.
4. Flash over USB, reboot and provision Wi-Fi using the chosen firmware's setup flow.
5. Wait for the device to become reachable and check firmware version, identity,
   capabilities and state before continuing.
6. On failure, show whether compilation, flashing or network connection failed,
   and offer a retry without claiming registration succeeded.

For WLED, install a compatible existing image and use its API. For custom GhostUI
firmware, implement a small versioned API. These are alternative firmware paths;
choose one for the first working light rather than building both immediately.

This is configuration and provisioning of known firmware. Arbitrary AI-generated
firmware for unknown hardware is outside the reliable onboarding promise.

### Establish the connection contract

A custom GhostUI firmware API should expose device identity, protocol version,
capabilities, current state and bounded commands. Proposed routes could be
`GET /identity`, `GET /capabilities`, `GET /state` and `POST /command`; these routes
are a design proposal and are not present on the ESP32 yet.

The capability manifest should include stable control IDs, labels, types, units,
ranges and steps. Firmware validates commands independently of the Mac. Use a
stable generated device identifier; do not rely solely on its current IP address.

For a WLED adapter, translate the existing WLED API into GhostUI's capability
contract instead of requiring WLED to implement the proposed custom endpoints.

The first milestone can expose integer brightness. Explicitly design power and
color representations before adding them: the current shared schema only supports
integer numeric sliders, not boolean switches or RGB color pickers.

The phone should keep talking to the Mac during this extension. The Mac owns device
transports and any USB flashing. Direct phone-to-device communication would be a
separate deployment change, not necessary to prove the new-device pipeline.

### Verify and bind the physical object

Read the device's identity, capabilities and state, then ask the user to confirm a
visible identification action such as a brief low-brightness blink. The action
must target the selected connection and be confirmed by the user. A successful HTTP
response alone does not prove which physical light responded.

After confirmation, create the device-instance record and prompt for visual views.
Associate every saved view with that instance. Reuse the working boxed multi-view
enrollment, YOLOE detection and local tracking. A small or featureless illuminated
ring may be visually harder than the speaker; enroll its housing and surrounding
fixed structure when appropriate, and test recognition under changed light colors.
A marker or manual selection remains a reasonable fallback if appearance is weak.

### Make controls and interact

The integration returns verified capabilities. The existing validation layer
rejects unknown controls and values outside permitted ranges. Gemini may propose
a layout; validate it and fall back to a deterministic template when needed.
Native AR now consumes the validated layout and caches successful generation on the Mac for offline reuse. Generation runs automatically on connection when the Mac has internet access.

During normal use, opening AR starts detection using saved enrollment. A highlight
indicates a selectable match. Pinch selection opens the device's controls. Pinch a
slider thumb and drag vertically to preview, then release to send the command.
Show the confirmed state or an error; do not leave an unconfirmed preview looking
like a successful physical change. Keep touch controls as an alternative.

For a new light, the UI must render its capabilities rather than volume, bass and
treble labels. For multiple registered devices, show which instance is selected
and keep commands bound to it until the user leaves or changes selection.

## Where contributors should work

| Responsibility | Current code location | Next extension |
| --- | --- | --- |
| Integration definitions | `ghostui_backend/integrations/catalog.py` | Register only tested executable integrations |
| Device protocols | `ghostui_backend/integrations/` | Add WLED or a GhostUI firmware light adapter |
| Capability validation | `ghostui_backend/contracts.py` | Extend types jointly with both renderers |
| Serialized control and confirmation | `ghostui_backend/service.py` | Keep transport operations on the worker |
| Registration orchestration | `ghostui_backend/onboarding/service.py` | Add instance lifecycle and setup steps |
| Phone routes | `ghostui_backend/server.py` | Add instance-scoped onboarding and control routes |
| Recognition and saved views | `ghostui_backend/recognition.py` | Bind storage to persistent instance IDs |
| Generated browser UI | `ghostui_backend/generation.py` and `web/` | Reuse validated capabilities |
| Phone transport and models | `ghostUI/ghostUI/Core/` | Add shared instance and setup models |
| Native registration | `ghostUI/ghostUI/Features/Onboarding/` | Build the Add device screens |
| AR and recognition | `ghostUI/ghostUI/Features/AR/` and `Recognition/` | Keep object association independent of transport |
| Gesture controls | `ghostUI/ghostUI/Features/Gestures/` | Render new capability types when supported |

Create a dedicated provisioning module when implementing firmware setup. Keep
compile/flash operations out of recognition, generic command handlers and LLM
layout generation. Existing `adapters/` files are compatibility imports; new adapter
implementations belong in `integrations/`. See `ARCHITECTURE.md` for the module map.

Current phone APIs include `/mobile/capabilities`, `/mobile/state`,
`/mobile/command`, `/mobile/vision` and enrollment/detection routes.
`GET /mobile/onboarding` reports the selected integration and enrollment summary.
`POST /mobile/onboarding/verify` with `{}` checks a fresh readable state. It reports
physical identity as unconfirmed and does not persist completion of the wizard.

## Recommended work order

### Milestone 1 Prove a real second device

Identify the board and ring, verify wiring, install one known firmware path and
control brightness from the Mac. Add the real light adapter and reuse the existing
phone controls, visual enrollment and gesture HUD. Initially select it at server
startup; do not delay this test for a polished registration wizard.

**Done when:** a phone gesture changes the real light and the app displays confirmed
state, using the same shared pipeline as Marshall. Demo light simulation does not
count as this milestone.

### Milestone 2 Add persistent registration

Create device-instance storage with integration ID, unique device ID, connection
configuration, firmware/protocol version and visual-enrollment association. Add
instance-scoped routing and the phone integration/device picker. Define migration
for existing speaker enrollment before changing its ID.

**Done when:** two saved device records cannot overwrite each other's enrollment
or send commands to the wrong target, and registration survives backend restart.

### Milestone 3 Automate the known firmware setup

Build the hardware recipe form and Mac USB compile/flash flow, then add network
setup, discovery and the identification blink. Keep supported board and LED choices
small until recovery behavior is tested.

**Done when:** a new supported ESP32 can reach verified control without the user
editing firmware source. Record board, firmware version and configuration used.

### Milestone 4 Polish and expand

Finish the registration wizard, add discovery improvements, handle reconnects,
and extend control types for power and color. Evaluate Matter or manufacturer APIs
as additional integrations. REA-assisted reverse engineering belongs in developer
adapter research, followed by physical validation before catalog inclusion.

## Reliability and security expectations

The current demo uses bearer-authenticated HTTP on a trusted LAN. It is not an
internet deployment design. Add encrypted transport and a credential-storage plan
before broader distribution. Keep Wi-Fi credentials, pairing tokens and API keys
out of committed files and firmware build logs. Do not bake per-user credentials
into shared firmware artifacts.

Read-only verification must remain distinct from physical confirmation. Never
write speculative commands to an unknown endpoint. Restrict firmware flashing to
an explicitly selected board and approved operation. A firmware update must not
silently replace a commercial device's software.

Test lost connectivity, invalid state, failed commands, malformed capabilities,
wrong device selection, failed flashing and failed discovery. A known device that
cannot currently connect should remain registered with an offline status.

## First contributor session

1. Read this guide and `ARCHITECTURE.md`, then run the simulated light.
2. Run `.venv-vision/bin/python -m unittest discover -s tests -v`.
3. Run the existing Marshall demonstration if hardware is available; preserve it
   as the comparison for shared behavior.
4. Confirm the ESP32 model and ring specification, then select the first firmware
   path. The immediate task is real light control through an adapter.
5. Build one milestone at a time and record physical test results separately from
   unit-test or compiler results.

## Technology references

- WLED API: https://kno.wled.ge/interfaces/json-api/
- WLED supported controllers: https://kno.wled.ge/basics/compatible-controllers/
- Espressif serial flashing tooling: https://github.com/espressif/esptool-js
- NeoPixel wiring and electrical guidance: https://learn.adafruit.com/adafruit-neopixel-uberguide/best-practices
- Alexa integration comparison: https://developer.amazon.com/docs/alexaplus/smarthome/development-options/

External references describe the underlying technologies. Planned GhostUI features
in this guide still require implementation and device testing.

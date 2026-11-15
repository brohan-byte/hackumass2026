# Sony XM5 demo: Mac playback volume

This fallback controls **Mac playback volume for the selected XM5 audio output**.
It does not expose Sony noise cancellation, EQ or other private settings. The
control is labeled **Mac volume** and the device **Sony XM5 · Mac playback**.
Play audio from the Mac to demonstrate the change; phone playback is separate.

## Start

The shared `data/phone-setup-demo` profile now offers **Sony XM5 · Mac playback**
in **Register object**. Connect the headphones to the Mac and select them as the
Sound Output, then restart the usual server command:

```sh
.venv-vision/bin/python app.py --data-dir data/phone-setup-demo --port 8783 --lan
```

Choose the XM5 on the phone, test volume with audio playing from the Mac, confirm
and save visual views. The connection is checked before a verified device record
is saved; an unavailable XM5 remains a setup choice and does not affect the light
or speaker. This profile option is stored in `registration-options.json`.
The Mac playback helper is already built on this development machine.

## Standalone diagnostic launch

From `hackumass`, connect the XM5 in macOS Bluetooth and select it in **System
Settings → Sound → Output**. Keep the Mac and iPhone on the same working Wi-Fi.

```sh
.venv-vision/bin/python tools/setup_mac_playback.py
data/sony-sdk/bin/ghostui-mac-playback --probe
.venv-vision/bin/python app.py --device sony-playback \
  --data-dir data/sony-demo --port 8782 --lan
```

The probe only reads. It must identify the XM5 and return volume in 0–100.
If needed, `data/sony-sdk/bin/ghostui-mac-playback --list` lists audio outputs;
`--select-xm5` explicitly selects the single connected XM5 as the Mac output.
The adapter refuses startup and subsequent commands when another output is
selected. It stores the audio device UID and never silently switches to speakers.

In the phone's connection settings use the Mac server URL with port **8782** and
the pairing token printed by this server. Then:

1. Tap **Register object → Sony XM5 · Mac playback**.
2. Test the volume slider while listening to Mac audio; confirm the device.
3. Draw and save the headphone views, then finish registration.
4. Point the camera at the headphones; tap/pinch the outline for the volume HUD.

The existing automatic Gemini call generates the native AR layout from the
adapter capabilities and caches it. Detection and gestures use the same pipeline
as Marshall/WLED. Headphone recognition still needs physical enrollment and a
real phone test. The separate registry preserves the original demo devices.

After registration, restart without re-registering the connection:

```sh
.venv-vision/bin/python app.py --data-dir data/sony-demo --port 8782 --lan
```

## Experimental direct Sony protocol

`sony` is a separate experimental integration using the MIT-licensed
[SonyHeadphonesClient](https://github.com/mos9527/SonyHeadphonesClient), pinned to
`3c8f3330c85d45c29e7b76f718082a8d4fe402f1`. Build with
`tools/setup_sony.py`, then read-test with `tools/probe_sony.py`. Setup copies
the upstream license and records the binary checksum under `data/sony-sdk`.

The native probe successfully read WH-1000XM5 firmware 1.1.3 and its 0–30 volume,
but repeated Classic Bluetooth connections timed out on this Mac. It is not the
deadline demo path. The fallback has no dependency on this SDK or private Sony
protocol, and no automatic fallback occurs between the two integrations.

Neither path is universal Bluetooth adapter generation. This demo reuses a known
Mac audio API; Gemini designs the validated UI rather than inventing protocols.

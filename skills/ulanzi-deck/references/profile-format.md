# Ulanzi Studio profile format (on disk)

Verified against Ulanzi Studio 3.4.4 on Windows 11 with a D200H: profiles written this way
were loaded, re-saved by the app, and shown on the device. macOS uses the same app (Qt), so
the format is expected to match, but its data folder is not verified (see platforms.md).
Read this when `ulanzi.py` cannot express something and you need to inspect or hand-check
a profile, or when an app update changes the format.

## Contents
1. Data folder layout
2. Profile and page manifests
3. Key ids and the D200H grid
4. Action catalog
5. Config files
6. Learning an unknown action ("calibration")

## 1. Data folder layout

```
<data root>/                     Windows: %APPDATA%\Ulanzi\UlanziDeck
  Config/device_source.json      devices the app has seen (Model, Name, Type, UUID)
  Config/setting_source.json     per-device settings incl. CurrentProfile (by NAME), Brightness
  ProfilesV2/<uuid>.ulanziProfile/
    manifest.json                profile manifest
    icon_*.png                   profile icon (48x48)
    Profiles/<pageUuid>/
      manifest.json              page manifest
      Images/*.png               key art referenced by the page
  logs/, Plugins/, System/Plugins/   (app-managed)
```
Folder sub-pages live under `Profiles/` too, but are **not** listed in the profile's
`Pages.Pages` array; a `page.folder` action points at them by uuid.

## 2. Manifests

Profile `manifest.json`:
```json
{"Device":{"Model":"D200H","UUID":"<device uuid from device_source.json>"},
 "Icon":"icon_profile.png","Name":"Dev & Stream",
 "Pages":{"Current":"<page uuid>","Pages":["<page uuid>","<page uuid>"]},"Version":2}
```
Page `manifest.json`:
```json
{"Controllers":[{"Actions":{},"Type":"Encoder"},
                {"Actions":{"0_0":{...action...},"1_0":{...}},"Type":"Keypad"}],
 "Icon":"","Name":"Dev"}
```
Action object:
```json
{"Action":"com.ulanzi.ulanzideck.system.open","ActionID":"<new uuid>",
 "ActionParam":{"Path":"..."},"LinkedTitle":true,"Name":"Claude",
 "Plugin":{"Name":"System","UUID":"com.ulanzi.deck.system","Version":"1.0"},
 "State":0,
 "ViewParam":[{"Icon":"<abs path with forward slashes>","IconRel":"Images/k0_0.png","Text":""}]}
```
- `ViewParam` has one entry per state (OBS toggles have two: off, on).
- `Text` is the title the app draws on top of the image. `ulanzi.py` bakes the label into the
  image and leaves `Text` empty so it is not drawn twice.
- Files are compact UTF-8 JSON without BOM.

## 3. Key ids and the D200H grid

Key id = `"<col>_<row>"`, columns 0-4 left to right, rows 0-2 top to bottom:
```
0_0 1_0 2_0 3_0 4_0
0_1 1_1 2_1 3_1 4_1
0_2 1_2 2_2 [ mini screen ]   <- 3_2 holds com.ulanzi.ulanzideck.smallwindow.window
```
13 programmable keys + the wide screen (clock/status). Key images are 196x196 PNG.
The original D200 uses the same 5x3 layout per community docs (not verified in Ulanzi Studio).
D200X and Dial have encoders (knobs) and other layouts. Layouts do not carry encoder actions:
`export` warns about them and `apply` writes an empty Encoder controller, which would unassign the
knobs. Treat these models as read-only until encoder support exists.

## 4. Action catalog

Prefix every action with `com.ulanzi.ulanzideck.`. Plugin objects:
System = `{"Name":"System","UUID":"com.ulanzi.deck.system","Version":"1.0"}`,
Pages = `{"Name":"Pages","UUID":"com.ulanzi.deck.page","Version":"1.0"}`,
OBS = `{"Name":"OBS Studio","UUID":"com.ulanzi.ulanzideck.obsstudio","Version":"1.0.0"}`.

| Action | Plugin | ActionParam | Notes |
|---|---|---|---|
| `system.open` | System | `{"Path": ...}` | Windows: `.lnk`, `.exe`, or `shell:AppsFolder\<AppID>` (Store apps). macOS: presumably the `.app` path (calibrate). |
| `system.close` | System | unknown | "close all instances of an app" (calibrate before use). |
| `system.website` | System | `{"Url": ...}` | any URL, incl. custom schemes (`steam://...`). |
| `system.hotkey` | System | `{"Hotkey": "Alt+Shift+F10"}` | Modifier names seen: `Win`, `Alt`, `Shift`, `Ctrl`. Format accepted by the app; firing on press not independently verified. macOS names unverified. |
| `system.switchhotkey` | System | unknown | toggles between two hotkeys (calibrate). |
| `system.multimedia` | System | `{"Hotkey": "Play_Pause"}` | also `Next_Track`, `Prev_Track`, `Volumn_Up`, `Volumn_Down`, `Volumn_Mute` (sic). |
| `system.text` | System | `{"Text": "...", "Enter": false}` | types the text. |
| `page.folder` | Pages | `{"ProfileUUID": "<sub-page uuid>"}` | opens a sub-page. |
| `page.back` | Pages | `{}` | returns from a sub-page (put it on `0_0`). |
| `page.next` / `page.prev` | Pages | `{}` | moves between top-level pages. |
| `smallwindow.window` | `{}` | `{"SmallViewMode": 1}` | the mini screen; keep it on `3_2`. |
| `obsstudio.<x>` | OBS | `{}` for the simple ones | Images (ViewParam entries) per the OBS plugin manifest: on/off toggles `stream`, `record`, `recordpause`, `virtualcam`, `replaybuffer`, `studiomode`, `sourcevisibility`, `filter` = 2; momentary `replaybuffersave`, `screenshot`, `transition`, `addchapter`, `scene`, `scenecollection`, `profile`, `scenetransition` = 2 (idle/pressed); `mediasourcecontrol` = 4; `audiomixer`, `audiomixervolume` = 1. `scene`, `sourcevisibility`, `filter`, `audiomixer*`, `scenecollection`, `profile`, `mediasourcecontrol`, `scenetransition` need params: calibrate. Needs OBS WebSocket (integrations.md). |

Other installed plugins (Multi Action, Key Logic, Pop key, Sound, Light Master, TC002 clock)
live in the install's `Ulanzi/UlanziDeck/System/Plugins/*/manifest.json`; read the manifest for
action UUIDs, and calibrate params before generating them.

## 5. Config files

- `device_source.json`: `{"Devices":[{"MacAddress":"","Model":"D200H","Name":"Deck Dock","Type":"D200H","UUID":"<serial, lowercase>"}]}`
- `setting_source.json`: `{"CurrentDeviceType":"<uuid>","Devices":[{"CurrentDevice":"<uuid>","CurrentProfile":"<profile NAME>","Brightness":86,"Font":{...},"ShowTitle":...}]}`
  Changing `CurrentProfile` while the app is stopped activates that profile on next start.

## 6. Learning an unknown action ("calibration")

The fastest reliable way to learn any action's exact JSON: create one key with that action in
Ulanzi Studio's UI (in a throwaway profile), then `export` that profile. Keys the tool knows come
out as their kind (with any extra settings in `params`); everything else comes out as a ready-to-use
`raw` key with the full action UUID, plugin object, params and state count. Copy that key into
your layout and restyle it (remove `image`/`images`/`title` to render it with your own label/glyph):
```json
"2_1": {"kind": "raw", "label": "Scene: BRB", "color": "#9B59B6", "glyph": "coffee",
        "action": "com.ulanzi.ulanzideck.obsstudio.scene",
        "plugin": {"Name": "OBS Studio", "UUID": "com.ulanzi.ulanzideck.obsstudio", "Version": "1.0.0"},
        "params": {"...": "as exported"}, "states": 2}
```
`keymap` is only a human summary: it shortens action names and omits the plugin object, so do not
copy from it.

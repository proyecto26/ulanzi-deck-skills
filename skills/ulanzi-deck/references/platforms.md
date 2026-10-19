# Platforms: Windows, macOS, Linux

What is verified where, and how to close the gaps safely. Official Ulanzi Studio exists for
Windows 10+ and macOS 12+ (Apple silicon and Intel). There is no official Linux app.

| | Windows | macOS | Linux |
|---|---|---|---|
| Official app | Ulanzi Studio (`UlanziDeck.exe`) | Ulanzi Studio (`/Applications/Ulanzi Studio.app`) | none |
| Data folder | `%APPDATA%\Ulanzi\UlanziDeck` **verified** | expected `~/Library/Application Support/Ulanzi/UlanziDeck` **unverified** | n/a |
| `ulanzi.py build` | yes | yes | yes (key art only) |
| `ulanzi.py apply` | yes (Ulanzi Studio 3.4, D200H) | worked on Ulanzi Studio 3.4.4 + D200H (macOS 26); still needs `--force-unverified` | no (community tools instead) |
| App icons | Windows shell (`.lnk`, `.exe`, Store apps) | `.icns` from the bundle, Quick Look fallback | `.desktop` Icon (PNG themes only) |
| Window screenshot | `scripts/win/capture_window.ps1` | `screencapture` (see below) | n/a |

The data folder is only accepted when it contains both `ProfilesV2/` and `Config/device_source.json`
(other vendors, e.g. Elgato on macOS, also use a `ProfilesV2` folder).

## Windows

- Install/update: `scripts/win/install.ps1` resolves the official download (the bare host
  `ulanzistudio.com/deck/download/windows` redirects to `cdn.ulanzistudio.com/...exe`; the `www`
  host has returned 504s), downloads it, and refuses to continue unless the Authenticode signature
  is valid and its subject CN is "Shenzhen Ulanzi Technology Co., Ltd.". `-Install` runs the NSIS
  installer silently (`/S`; UAC prompt possible). Run without `-Install` first and tell the user the
  version (it is in the printed file name: `Win_Ulanzi_Studio_V<version>.<date>.exe`).
- Run helper scripts with `powershell -NoProfile -ExecutionPolicy Bypass -File <script> ...`; the
  default Windows policy blocks unsigned scripts.
- Launch targets: prefer the Start Menu/Desktop `.lnk` (it keeps the working directory; OBS fails
  to start without it). Store/MSIX apps have no file: use `shell:AppsFolder\<AppID>`. `find-apps`
  picks the right one for you.
- The app minimises to the tray; `UlanziDeck.exe` keeps running when the window is closed.
- USB: the D200H enumerates as `VID_2207&PID_0019` with bus description "ulanzi".
- Screenshot of the app: `scripts/win/capture_window.ps1 -Out <png>` uses `PrintWindow`, which
  works even when the window is covered (screen-copy captures whatever is on top).

## macOS (calibrate before writing)

Nothing on macOS has been verified with these scripts. Do this once per Mac before `apply`:

1. Install uv (`brew install uv` or https://docs.astral.sh/uv/) and run
   `uv run "<skill dir>/scripts/ulanzi.py" state`. (Avoid `pip install --user` on Homebrew Python, and
   Apple's `/usr/bin/python3` may be older than 3.10.)
   If DATA is "not found": with Ulanzi Studio open, run
   `find ~/Library -maxdepth 4 -type d -name ProfilesV2 2>/dev/null`, pick the folder that belongs to
   Ulanzi (its parent also has `Config/device_source.json`), and export
   `ULANZI_DECK_ROOT=<the parent of ProfilesV2>`.
2. In Ulanzi Studio, make a throwaway profile with one **Open** key (pick any app), one **Hotkey**
   key, and one key of every other action type the planned layout uses (e.g. an OBS Record key).
   Run `export --profile "<that profile>" -o calib.json --keep-paths` and read it.
3. Compare with Windows: is the open `path` the `.app` path? How are modifiers spelled (`Cmd`,
   `Command`, `⌘`)? Does `ViewParam.Icon` hold an absolute path (look in the page manifest)? If
   anything differs from references/profile-format.md, adjust the layout (per-OS fields) before generating.
4. `apply --force-unverified` is always required on macOS (the check cannot know you calibrated):
   pass it only after steps 2-3 matched, use a **new profile name** first, check it in the app, and
   keep the printed backup path for `restore`.
- Observed on Ulanzi Studio 3.4.4 with a D200H (macOS 26), from the stock profiles and the
  bundled plugins, then confirmed by an `apply` of 5 pages (2 pages, 3 folders, app/web/hotkey/media/OBS
  keys) that the app re-saved (`VERIFY ... -> OK`):
  - The data folder is the expected `~/Library/Application Support/Ulanzi/UlanziDeck`.
  - Open keys store the `.app` bundle path (`/Applications/OBS.app`), as `find-apps` resolves it.
  - Hotkeys use symbols: `"⇧ ⌘ 5"` (see layout-schema.md, Portability).
  - `ViewParam.Icon` is an absolute path; top-level pages add `IconRel`, folder pages `IconEx`.
  - Folder pages carry an extra non-key `"Icon"` entry in `Keypad.Actions` (ignored by the tool).
  - The OBS plugin (`System/Plugins/com.ulanzi.obsstudio.ulanziPlugin`) has the same UUID,
    version 1.0.0 and action ids as on Windows.
  - The bundle has no version keys; `state` reads the version from the data folder's `version.txt`.
- Hotkeys need Accessibility permission for Ulanzi Studio (System Settings > Privacy & Security >
  Accessibility). The SDK warns that launching it with `open --args` can break that permission.
- Screenshot: `screencapture -x -o -l <window id> <png>` captures just the Ulanzi Studio window with
  no clicks (get the id from `CGWindowListCopyWindowInfo`, owner name `UlanziDeck`, e.g. with a
  `swift -e` one-liner); `screencapture -w <png>` lets the user click the window instead. Show the PNG with Read.

## Linux (no Ulanzi Studio)

Be direct: Ulanzi Studio does not run on Linux, and Wine is not a real option (the app talks to
the device over USB). Community options, all unofficial; read each project's README for current
install steps instead of relying on this summary:

1. **OpenDeck + "OpenDeck Ulanzi D200 Driver"** (gitlab.com/glmagalhaes.mail/rs-ulanzi-d-200-linux,
   AGPLv3, Rust, pre-1.0). OpenDeck (github.com/nekename/OpenDeck) is an open-source stream-controller
   app; this plugin explicitly lists the **D200 and D200H** (USB `2207:0019`; the D200H adds two
   Genesys USB hubs `05e3:0610`). Install the plugin from OpenDeck's marketplace or "Install from
   file". Known issues: the wide key's icon is stretched, there is a non-functional "ghost" key at
   the bottom-right, and the wide key may need a firmware update, which only Ulanzi Studio
   (Windows/macOS) can do. USB permissions (udev) may need a rule: check the plugin's repo/issues.
2. **`aleyvag/ulanzi-d200h-linux`** (MIT, Python/uv): a HID bridge written **only for the D200H**.
   Pages are YAML files, it can import Windows `.ulanziDeckProfile` exports, runs as a systemd user
   service, and has Spotify, multi-actions and auto icons. Limits stated by its README: no OBS
   integration (only generic key/shell/app actions) and X11-focused (Wayland largely untested).
3. **`racerxdl/ulanzi-d200-linux`** (MIT, Python): udev rule, daemon + local web UI, YAML config
   at `~/.config/ulanzi/config.yaml`, buttons 0-12 plus the wide display, 196x196 PNG icons,
   actions `command`, `app` (.desktop), `key` (xdotool; does not reach Wayland apps), `obs`
   (WebSocket; set port 4455 for OBS 28+). It documents only the **D200**.
4. Run Ulanzi Studio on a Windows/macOS machine (the device shows its profile only while the app runs).

The community projects disagree about D200 vs D200H compatibility: the OpenDeck plugin calls the
D200H "identical to the D200 but with two USB hubs" (same USB id `2207:0019`), while
`aleyvag/ulanzi-d200h-linux` says the two "speak different USB HID protocols". So for a **D200H**,
recommend one of the two projects that name it explicitly (OpenDeck plugin if OBS control matters,
aleyvag's bridge otherwise), and present racerxdl only as a D200 tool. Attribute each claim to its project.
- `ulanzi.py build` still works on Linux: it renders `pages/<id>/k<col>_<row>.png` (196x196) and a
  preview, usable as button images in either community tool.
- For a mic-mute key on PipeWire (Ubuntu 22.10+), a command such as
  `wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle` works on both Wayland and X11.
- Do not flash firmware or use the device's debug interfaces; out of scope and can brick it.

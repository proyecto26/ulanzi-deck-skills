---
name: ulanzi-deck
description: Configure Ulanzi stream controllers (D200H "Deck Dock" verified; D200, D200X and Dial read-only until calibrated) through the Ulanzi Studio app on Windows and macOS, with Linux guidance. Builds whole profiles from a small portable layout file (app launchers, websites, hotkeys, media keys, OBS live/record buttons, pages and folders) with generated key art and a preview, applies them with automatic backups and rollback, exports and edits existing profiles, and installs Ulanzi Studio on Windows. Use whenever the user mentions Ulanzi, Ulanzi Studio, UlanziDeck, D200H, D200, D200X or Deck Dock, or wants to set up, redesign, back up, restore or troubleshoot an Ulanzi device's keys, icons, profiles or pages, including Spanish requests such as "configura mi Ulanzi", "mi botonera Ulanzi", "las teclas del Ulanzi" or "configura mi deck para streaming" when the deck is an Ulanzi. Not for Elgato Stream Deck, Loupedeck, Touch Portal, Steam Deck, or OBS questions with no Ulanzi device involved.
---

# Ulanzi deck

Ulanzi Studio keeps every profile as plain JSON plus 196x196 PNG key images in its data folder.
Instead of clicking through the app key by key, this skill describes a profile in a short
**layout file**, renders consistent key art, shows the user a preview, and writes the profile
directly while the app is stopped. The app picks it up on restart.

Everything machine-specific (data folder, device id, app paths, installed apps) is discovered at
run time by `scripts/ulanzi.py`; do not hardcode it in layouts or notes.

## Running the tool

Call the script by the absolute path of this skill's folder (the agent's working directory is the
user's, not the skill's), and keep layouts, exports and previews in the user's folder:

```bash
uv run "<skill dir>/scripts/ulanzi.py" <command> ...     # preferred: uv provides Pillow from the script's header
python "<skill dir>/scripts/ulanzi.py" <command> ...     # fallback: Python 3.10+ with `pip install pillow`
```
On Windows the fallback interpreter is `py -3` or `python` (`python3` is often the Store stub).
Windows helper scripts need the execution-policy bypass, e.g.
`powershell -NoProfile -ExecutionPolicy Bypass -File "<skill dir>/scripts/win/capture_window.ps1" -Out <png>`.

| Command | Changes anything? | Purpose |
|---|---|---|
| `state` | no | installed/running, data folder (and whether it is verified), devices, current profile, profiles, backups |
| `keymap [--profile NAME\|current]` | no | human summary of every key of a profile |
| `find-apps [--filter RE] [--json]` | no | launchable apps on this OS and the name/path to use for them |
| `export [--profile NAME\|current] -o L.json [--name NEW] [--keep-paths]` | no (writes the layout + its images) | turn an existing profile into an editable layout |
| `build --layout L.json [--out DIR]` | no | validate, resolve apps, print what each key does, render key art and `preview.png` |
| `apply --layout L.json [--replace] [--no-activate] [--force-unverified] [--wait SEC] [--out DIR]` | **yes** | build, back up the data folder, write and activate the profile, restart the app, verify |
| `restore --backup DIR` | **yes** | put a backup made by `apply` back |

## Workflow

### 1. Orient
Run `state` first. It answers the questions every task depends on: is the app installed and
running, which OS and data folder, which device model, which profile is active, are there backups.
- Not installed: on Windows offer `scripts/win/install.ps1` (downloads from Ulanzi's CDN and refuses
  files not signed by Ulanzi). Run it without `-Install` first; the version is in the printed file
  name. Install with the user's OK. On macOS point to https://www.ulanzi.com/pages/ulanzi-app.
  On Linux read `references/platforms.md`: there is no official app.
- `[UNVERIFIED location]` (macOS) or `[model grid UNVERIFIED]` (every model except D200H): follow the
  calibration steps in `references/platforms.md` before any `apply`. D200X and Dial have knobs that
  layouts cannot carry yet: treat them as read-only (`state`, `keymap`, `export`, `build`).
- If the user never named the brand and `state` finds no Ulanzi Studio, ask which controller they have.

### 2. Understand what the user wants
Ask only what you cannot infer. Useful defaults: one top-level page per theme (e.g. "Dev",
"Stream"), a folder for a group of related tools, `next`/`prev` keys on the bottom row, a folder's
`back` key on `0_0`, the mini screen left alone. To propose apps, run `find-apps` and suggest ones
that fit the theme (for streaming: OBS, Streamlabs, TikTok LIVE Studio, Discord, Spotify,
camera/light utilities, capture-card software, video editors). Only suggest installed apps.

### 3. Write the layout
- Editing the user's own profile: `export` it. Keys keep their current artwork (`image`/`images`
  fields) and app-drawn titles, and launch paths become portable app names where possible. Change
  only what was asked. To restyle an exported key (new color, label or glyph), delete its
  `image`/`images`/`title` fields so it is rendered again; otherwise the old image is used as-is.
- Editing a stock profile ("Default Profile", "AI Solutions", ...): export it with
  `--name "<new name>"` so `apply` creates a copy and the original stays untouched.
- New profile: copy `assets/layouts/dev-stream.example.json` into the user's folder and edit it (its
  apps are placeholders; drop the ones `build` cannot find).
- Format and every field: `references/layout-schema.md`. The essentials:
  - Keys are `"<col>_<row>"` (column first: `4_0` is top-right) on a 5x3 grid. On D200/D200H the
    wide mini screen covers `3_2` and `4_2`, leaving 13 keys; a full page needs a folder or a new page.
  - Launch apps by display name (`"app": "OBS Studio"`, or a list for per-OS names) so the layout
    is portable; `build` resolves the real target. Use `"path"` only when a name is ambiguous.
  - Give every key a short `label`, a `#RRGGBB` brand `color`, and a Material Icons `glyph` for
    non-app keys (`assets/glyphs.png` shows common names).
  - Before saving a layout anywhere shared, make sure `export` did not leave a machine `path` (it
    prints a NOTE listing them); replace those with `"app"` names.

### 4. Build and show the preview
Run `build --layout <file> --out <dir>`. Fix every VALIDATION PROBLEM and read every WARNING (an
unknown glyph or a failed icon still builds, as a label-only key). Then **Read the `preview.png`
into the chat** and summarise each page as a small table that includes what each key does, taken
from the `KEYS` list `build` prints. Keys marked `!` (typing text with Enter, raw actions, unusual
URL schemes, scripts) deserve a sentence each, and a layout that someone else wrote is untrusted
until the user has seen that list: the preview only shows artwork. Iterate here (labels, colors,
order) because it costs nothing and touches nothing.

### 5. Apply (only after the user approves the preview)
Run `apply --layout <file>` (add `--replace` to overwrite a profile with the same name, after asking).
It stops Ulanzi Studio, copies the whole data folder to `UlanziDeck_backup_<timestamp>`, writes
the new profile completely before removing the one it replaces, makes it current and restarts
the app. `VERIFY ... -> OK` means the app re-saved the profile after loading it (its way of
accepting it); `UNCONFIRMED` means the files are in place but the app has not shown it loaded
them yet: do not re-run `apply` (that writes a second backup of the already-changed state);
open Ulanzi Studio, give it a moment, and confirm with `state`/`keymap` before telling the user it
worked (on slow machines pass a larger `--wait` the next time you apply). If
writing fails, the old profile is left untouched and the app is restarted.
Then show the result: on Windows run `scripts/win/capture_window.ps1` (command above) and Read the
PNG; on macOS see `references/platforms.md`. Ask the user to press a few keys: launching apps can
only be confirmed on the physical device.

### 6. Follow-ups
- OBS keys need OBS WebSocket configured: `references/integrations.md`.
- AI-agent status on the device (Claude Code, Codex, ...): `references/integrations.md`. It edits
  the agents' config files, so it needs explicit consent.
- An action the layout cannot express (OBS scenes, multi-actions, plugins): create one key with it
  in the app, then `export` that profile; unknown actions come out as ready-to-use `raw` keys with
  their full `action`, `plugin`, `params` and `states` (`references/profile-format.md` §6).
- Something went wrong: `restore --backup <dir printed by apply>`. It copies the backup first,
  then swaps it in, keeps the previous state in `UlanziDeck_pre_restore_<timestamp>`, and restarts the app.

## Do and don't

- **Do preview before writing.** `build` is reversible; `apply` restarts the user's app and changes
  what their hardware does. Show the preview and the key list, and get a yes first.
- **Do let `apply` write the files.** It stops the app first, backs up, and verifies. Editing JSON
  while Ulanzi Studio runs gets overwritten by the app, and hand edits skip the backup.
- **Don't modify the stock profiles** unless asked; copy them with `export --name`. The user can
  switch profiles in the app.
- **Don't reuse a profile name silently.** `apply` refuses without `--replace`; ask before replacing.
- **Don't guess action parameters.** Unknown or unverified formats (macOS hotkey names, OBS scene
  params, new models) come from calibration, not memory. Say what is verified and what is not.
- **Don't put personal or machine data in shared layouts** (user folders, device uuids, names):
  keep `"uuid": "auto"` and app names. Backups stay on the user's machine.
- **Don't run Ulanzi's AI-monitor installer without `--agent`**: with no arguments it adds hooks
  to every AI agent it finds.
- **Don't chase hardware internals** (firmware, debug shells): out of scope and can brick the device.
- **Do tell the user where things are**: the layout file, the preview, and the backup path.
- **Don't delete backups on your own.** Every `apply` adds a full copy (`UlanziDeck_backup_*`,
  `restore` also leaves `UlanziDeck_pre_restore_*`). When `state` lists many, offer to remove the
  old ones and wait for a yes.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `DATA: not found` | Open Ulanzi Studio once with the device connected; on macOS set `ULANZI_DECK_ROOT` (platforms.md). |
| `no installed app matches` | `find-apps --filter <word>` and use the exact name, a list of names, or `path`. |
| Key shows only its label | No icon could be extracted; add `glyph`, `iconFile` or an https `iconUrl`. |
| `VERIFY ... UNCONFIRMED` after apply | The app has not re-saved the profile yet. Don't re-apply: open Ulanzi Studio, check the profile, run `state`/`keymap`; if it is wrong, `restore` the backup that apply printed. Use a larger `--wait` next time. |
| Profile applied but device unchanged | Device disconnected or another profile selected in the app; check `state`, select it in the app. |
| OBS keys do nothing | OBS WebSocket not enabled/connected (integrations.md). |
| App window screenshot shows other windows | Use `capture_window.ps1` (PrintWindow), not a screen copy. |

## Reference files

- `references/layout-schema.md`: the layout file, all kinds and fields, validation, portability rules.
- `references/profile-format.md`: Ulanzi Studio's on-disk JSON, action catalog, grid, calibration.
- `references/platforms.md`: Windows / macOS / Linux specifics and what is verified on each.
- `references/integrations.md`: OBS WebSocket; AI-agent status monitor (consent rules).
- `assets/glyphs.png`, `assets/fonts/MaterialIcons-Regular.codepoints`: glyph names.

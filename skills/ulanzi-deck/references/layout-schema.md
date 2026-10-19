# Layout JSON (input to `ulanzi.py build` / `apply`)

A layout describes a whole profile in a small, portable file. `export` produces one from an
existing profile; `assets/layouts/dev-stream.example.json` is a complete example.

```json
{
  "profileName": "Dev & Stream",
  "device": {"model": "D200H", "uuid": "auto"},
  "pages": [
    {"id": "dev", "title": "Dev", "keys": { "0_0": { ...key... } }},
    {"id": "media", "title": "Media", "folder": true, "keys": { ... }}
  ]
}
```
- `profileName`: shown in Ulanzi Studio; `apply` refuses to overwrite a profile with the same
  name unless `--replace`.
- `device.uuid`: `"auto"` takes the first device of that model listed in `device_source.json`
  (devices the app has seen, connected or not); set an explicit uuid if several are listed.
- Page `id`: letters, digits, `-` and `_` only (it becomes a folder name in the build output).
- Pages without `"folder": true` are top-level pages in order (navigate with `next`/`prev`).
  Pages with `"folder": true` are sub-pages opened by a `folder` key; give them a `back` key on `0_0`.
- Key ids are `"<col>_<row>"`, column first (references/profile-format.md §3). On D200/D200H the
  wide mini screen covers `3_2` and `4_2`; it is added automatically (13 programmable keys).
- Optional page `screen`: the mini screen's ActionParam (what `export` keeps when it is not the
  default `{"SmallViewMode": 1}`).

## Key fields (all kinds)

| Field | Meaning |
|---|---|
| `kind` | one of the kinds below (required) |
| `label` | text baked into the bottom of the key (keep it under ~12 characters) |
| `color` | `#RRGGBB` (or `#RGB`) accent; tints the key background and border. Color names are rejected |
| `glyph` | Material Icons name for the key art (`mic`, `videocam`, `folder`...). Full list: `assets/fonts/MaterialIcons-Regular.codepoints`; preview of common ones: `assets/glyphs.png` |
| `badge` | short text pill instead of an icon (e.g. `"LIVE"`) |
| `iconFile` | local image to use as the icon (relative to the layout file, env vars allowed; must open as an image) |
| `iconUrl` | `https://` image downloaded once (15 s timeout, 5 MB cap) and used as the icon |
| `image` | a finished 196x196 key image used as-is (what `export` writes for one-state keys) |
| `images` | finished images, one per state, in ViewParam order (what `export` writes for multi-state keys) |
| `title` | (with `image`/`images`) title the app draws over the image; `export` keeps it from the original key. Rendered keys have their label baked in instead |
| `states` | (kind `raw`) number of state images to produce when no `images` are given |
| `params` | extra ActionParam fields merged into the action: calibrated settings (e.g. an OBS scene name), and anything `export` found that the kind does not map itself |

Icon priority: `image`/`images` > `iconFile` > `iconUrl` > the app's own icon (kind `app`) > `badge` > `glyph`.
State images: OBS keys get as many images as the OBS plugin declares (toggles: off + "ON";
momentary actions: idle + highlighted); everything else gets one, unless `images`/`states` say otherwise.

Validation (`build` exits 2, `apply` refuses): no pages, no top-level page, duplicate or unsafe
page ids, keys outside the grid or on the mini screen, unknown kinds, missing required fields,
bad colors, unreadable `iconFile`, non-https `iconUrl`, folder targets that do not exist, apps that
cannot be resolved (including Store AppIDs the shell does not list). Pages without keys are allowed (warning).
Setting `glyph` on an `app` key skips the app icon. To restyle a key that has `image`/`images`,
remove those fields (and `title`) so it is rendered from `label`/`color`/`glyph`.

`build` also prints a `KEYS` list (what each key does). `!` marks keys worth a second look before
approving: typing text with Enter, `raw` actions, non-http(s) URLs, script files.

## Kinds

| kind | Required fields | Example |
|---|---|---|
| `app` | `app` (display name, string or list of alternatives) **or** `path` | `{"kind":"app","label":"OBS","app":["OBS Studio","OBS"]}` |
| `web` | `url` | `{"kind":"web","label":"GitHub","url":"https://github.com","glyph":"code"}` |
| `hotkey` | `hotkey` | `{"kind":"hotkey","label":"Mute mic","hotkey":"Ctrl+Shift+M","glyph":"mic_off"}` |
| `media` | `media`: `Play_Pause` `Next_Track` `Prev_Track` `Volumn_Up` `Volumn_Down` `Volumn_Mute` | `{"kind":"media","label":"Play","media":"Play_Pause","glyph":"play_arrow"}` |
| `text` | `text`, optional `enter` | `{"kind":"text","label":"Hi chat","text":"Hello chat!","enter":true}` |
| `folder` | `target` (a page id with `"folder": true`) | `{"kind":"folder","label":"Media","target":"media","glyph":"folder"}` |
| `back`, `next`, `prev` | none | `{"kind":"next","label":"Stream","glyph":"arrow_forward"}` |
| `obs` | `obs` (`stream`, `record`, `virtualcam`, `replaybuffersave`, ...) | `{"kind":"obs","label":"Live","obs":"stream","badge":"LIVE"}` |
| `raw` | `action`, optional `plugin`, `params` | any action learned by calibration (profile-format.md §6) |

## Portability

- Prefer `"app": "<display name>"` over `"path"`: `build` resolves the name on the current OS
  (Windows Start menu / Store apps, macOS `/Applications`), so one layout works on both.
  Run `ulanzi.py find-apps --filter <regex>` to see the exact names on this machine.
- Use a list when names differ per OS: `"app": ["OBS Studio", "OBS"]`.
- `app`, `path`, `hotkey`, `url`, `text` also accept a per-OS object:
  `"hotkey": {"windows": "Win+Shift+S", "macos": "Cmd+Shift+4"}` (macOS hotkey spelling is
  unverified: calibrate one hotkey first).
- `path` expands environment variables (`%APPDATA%\\...` on Windows, `$HOME/...` elsewhere).
- Never commit machine-specific paths, device uuids or user names into a shared layout:
  keep `uuid: "auto"` and app names.

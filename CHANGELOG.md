# Changelog

## Unreleased

### Fixed (macOS)
- `keymap` and `export` crashed on folder pages: the macOS app stores a non-key `"Icon"` entry in
  `Keypad.Actions`; only `<col>_<row>` keys are read now.
- `state` showed `version None`: the macOS bundle has no version keys, so the version comes from the
  data folder's `version.txt`.
- `export` falls back to `IconEx` (used by the macOS app on folder pages) when `IconRel` is missing.
- Example layout and schema used `Cmd+Shift+4` for macOS hotkeys; Ulanzi Studio stores `⇧ ⌘ 4`.
  The example's Docker key also accepts the macOS name `Docker`.

### Verified
- `apply` on macOS (Ulanzi Studio 3.4.4, D200H, macOS 26): 2 pages and 3 folders with app, web,
  hotkey, media and OBS keys, re-saved by the app (`VERIFY ... -> OK`). Observed on-disk formats
  are recorded in `references/platforms.md`.

## 0.1.0 — 2026-10-18

### Added
- `ulanzi-deck` skill: configure Ulanzi stream controllers (D200H verified) through Ulanzi Studio.
- `scripts/ulanzi.py` (Python 3.10+, PEP 723 header for `uv run`): `state`, `keymap`, `find-apps`,
  `export`, `build`, `apply`, `restore`.
  - Portable layouts: apps by display name (or per-OS alternatives), per-OS field values.
  - Key art and preview rendering with Pillow and bundled Material Icons.
  - Transactional apply: full backup, new profile written before the old one is removed, app
    restarted on failure, OK only when the app re-saves the profile.
  - Export keeps unmapped ActionParam fields, every state image, app-drawn titles and custom
    mini-screen settings, and writes portable app names instead of machine paths; encoder (knob)
    actions are not carried (export warns), so D200X/Dial stay read-only.
  - `build` prints what every key does and flags risky actions; validates page ids, colors,
    icon files/URLs (https only, timeout, size cap) and Store AppIDs.
  - Atomic `restore` (copy first, swap, roll back on failure); `apply` restarts the app if the backup fails.
  - Linux guidance: OpenDeck + "OpenDeck Ulanzi D200 Driver" (lists D200 and D200H) and racerxdl/ulanzi-d200-linux.
  - OBS state images per the OBS plugin manifest.
  - macOS writes require calibration (`--force-unverified`) even with `ULANZI_DECK_ROOT`.
- Windows helpers: shell icon extraction, app discovery, PrintWindow screenshot, verified installer download.
- References: layout schema, on-disk profile format, platforms (Windows/macOS/Linux), OBS and AI-monitor integrations.
- Multi-host packaging: Agent Plugins 1.0 `plugin.json`, Claude Code `.claude-plugin/`, Codex `.codex-plugin/`,
  `.agents/plugins/marketplace.json`; `scripts/check-manifests.sh` gate with a privacy scan.
- Offline unit tests and skill-creator evals.

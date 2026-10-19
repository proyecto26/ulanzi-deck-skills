# Changelog

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

# Integrations: OBS Studio and the AI-agent status monitor

## OBS Studio keys (`kind: "obs"`)

Ulanzi Studio talks to OBS through OBS WebSocket (built into OBS 28+). The keys do nothing
until both sides are set up:

1. Open OBS at least once (a never-launched OBS has no config and no scenes).
2. OBS > Tools > WebSocket Server Settings: enable the server, note port (default 4455) and the
   password. Do not paste the password into chat or files; the user types it into Ulanzi Studio.
3. In Ulanzi Studio, select any OBS key and fill in the connection in its settings panel.
4. Test `record` first (visible and harmless), then `stream`.
- Toggle actions (`stream`, `record`, `virtualcam`, ...) have two images; the device swaps them
  when OBS reports the state.
- `replaybuffersave` only works when Replay Buffer is enabled in OBS (Settings > Output).
- Scene/source keys need parameters: calibrate (profile-format.md §6) after the user has scenes.

## AI-agent status monitor (`ustudio-cli`)

Recent Ulanzi Studio versions bundle `ustudio-cli`, which shows an AI coding agent's state on the
device (idle, thinking, working, needs attention, error). It works by **adding hook commands to
the agent's own config files**:

| Agent | File it edits |
|---|---|
| Claude Code | `~/.claude/settings.json` (hooks on SessionStart, UserPromptSubmit, Pre/PostToolUse, Stop, Notification, PermissionRequest, PreCompact, ...) |
| Codex CLI | `~/.codex/hooks.json` and `~/.codex/config.toml` (Codex then asks to approve the hooks) |
| Gemini CLI, Cursor Agent, CodeBuddy, Kimi, Kiro, Copilot CLI | their settings/hooks files |

Its installer is `<install dir>/ustudio-cli/installers/install.js`, run with the Node runtime that
ships next to it (on Windows `<install dir>\nodejs\node.exe`, e.g.
`"<install dir>\nodejs\node.exe" "<install dir>\ustudio-cli\installers\install.js" --check --agent claude-code`;
the install dir is shown by `state`). Flags: `--check` (read-only status, JSON), `--dry-run`,
`--agent <id>` (repeatable: `claude-code`, `codex`, `gemini-cli`, `cursor-agent`, `codebuddy`,
`kimi-cli`, `kiro-cli`, `copilot-cli`), `--uninstall`.

Rules, because this changes how the user's AI tools behave:
- Ask before enabling it, naming each file that will change. Never decide this on the user's behalf.
- **Running install.js with no `--agent` registers hooks in every agent it finds.** Always pass
  `--agent` explicitly, and run `--check` / `--dry-run` first.
- Back up each config file it will touch before the change (for Codex: `~/.codex/hooks.json` and
  `~/.codex/config.toml`), and show the diff of every changed file afterwards.
- Hooks it adds are named `ulanzi-studio` (legacy: `ai-tool-state-monitor`); `--uninstall --agent X`
  removes them. If the app offers a UI toggle for this feature, prefer it over the CLI.
- Its manifest states that events are reduced to allowlisted metadata (no prompts, transcripts or
  tool inputs are forwarded). That is the vendor's claim; mention it as such.

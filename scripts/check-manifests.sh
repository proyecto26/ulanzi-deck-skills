#!/usr/bin/env bash
# Assert that every host manifest agrees on plugin identity and install wiring, and that the
# skill ships nothing machine- or person-specific.
#
# Checks name / version / description across:
#   plugin.json                      (Agent Plugins 1.0 — Cursor, Copilot CLI)
#   .codex-plugin/plugin.json        (OpenAI Codex)
#   .claude-plugin/plugin.json       (Claude Code)
#   .claude-plugin/marketplace.json  (Claude Code marketplace entry)
# plus the install wiring each host relies on, every skills/*/SKILL.md frontmatter, a privacy
# scan of skills/ (absolute user-home paths, e-mail addresses), and the real host validators
# that exist: `claude plugin validate` and the Agent Plugins 1.0.0 JSON schema.
#
# Usage: bash scripts/check-manifests.sh [--allow-skips]
#   exit 0 = every check ran and passed. A validator that cannot run fails the gate
#   unless --allow-skips is given (local convenience only, not for release).

set -euo pipefail

allow_skips=false
if [[ "${1:-}" == "--allow-skips" ]]; then
  [[ -n "${CI:-}" ]] && { echo "FAIL: --allow-skips is not permitted when CI is set"; exit 1; }
  allow_skips=true
fi
skipped=0
skip() {
  if $allow_skips; then echo "SKIP: $1"; skipped=$((skipped + 1)); else echo "FAIL: $1 (pass --allow-skips to tolerate locally)"; exit 1; fi
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
py=""
for cand in python3 python; do command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' 2>/dev/null && { py="$cand"; break; }; done
[[ -n "$py" ]] || { echo "python3 is required" >&2; exit 1; }

"$py" - <<'PY'
import glob, json, os, re, sys

def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

root      = load("plugin.json")
codex     = load(".codex-plugin/plugin.json")
claude    = load(".claude-plugin/plugin.json")
claude_mp = load(".claude-plugin/marketplace.json")
codex_mp  = load(".agents/plugins/marketplace.json")

name = root["name"]
entry = next((p for p in claude_mp["plugins"] if p.get("name") == name), None)
if entry is None:
    print(f"FAIL: .claude-plugin/marketplace.json has no entry named {name!r}"); sys.exit(1)

sources = {
    "plugin.json": root,
    ".codex-plugin/plugin.json": codex,
    ".claude-plugin/plugin.json": claude,
    ".claude-plugin/marketplace.json[entry]": entry,
}
errors = []
for field in ("name", "version", "description"):
    values = {label: src.get(field) for label, src in sources.items()}
    if len(set(values.values())) != 1:
        errors.append(f"{field} differs:\n" + "\n".join(f"    {k}: {v!r}" for k, v in values.items()))

if root.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
    errors.append("plugin.json $schema is not the Agent Plugins 1.0.0 schema URL")
portable_allowed = {"$schema", "name", "version", "description", "author", "homepage",
                    "repository", "license", "keywords", "extensions"}
extra = set(root) - portable_allowed
if extra:
    errors.append(f"plugin.json has non-portable top-level fields: {sorted(extra)}")

# Codex / Copilot catalog wiring
codex_entries = [p for p in codex_mp.get("plugins", []) if p.get("name") == name]
if len(codex_entries) != 1:
    errors.append(f".agents/plugins/marketplace.json must have exactly one entry named {name!r} (found {len(codex_entries)})")
else:
    ce = codex_entries[0]
    for field, want, got in (
        ("source.source", "local", (ce.get("source") or {}).get("source")),
        ("source.path", "./", (ce.get("source") or {}).get("path")),
        ("policy.installation", "AVAILABLE", (ce.get("policy") or {}).get("installation")),
        ("policy.authentication", "ON_INSTALL", (ce.get("policy") or {}).get("authentication")),
    ):
        if got != want:
            errors.append(f".agents/plugins/marketplace.json[{name}].{field} is {got!r}, expected {want!r}")
    if not ce.get("category"):
        errors.append(f".agents/plugins/marketplace.json[{name}] is missing 'category'")

# Claude marketplace: strict:true + auto-discovery, so the entry declares only source "./" and
# neither it nor plugin.json re-declares components.
if entry.get("source") != "./":
    errors.append(f".claude-plugin/marketplace.json[{name}].source is {entry.get('source')!r}, expected './'")
if entry.get("strict") is False:
    errors.append(f".claude-plugin/marketplace.json[{name}] sets strict:false; this plugin relies on auto-discovery")
for comp in ("skills", "commands", "agents", "hooks", "mcpServers"):
    if comp in entry:
        errors.append(f".claude-plugin/marketplace.json[{name}] must not declare '{comp}' (uses auto-discovery)")
    if comp in claude:
        errors.append(f".claude-plugin/plugin.json must not declare '{comp}' (uses auto-discovery)")

if codex.get("skills") != "./skills/":
    errors.append(".codex-plugin/plugin.json 'skills' should be './skills/'")

# Every skill: SKILL.md with name == folder name and a description.
skills = sorted(x.replace("\\", "/") for x in glob.glob("skills/*/SKILL.md"))
skills = [s for s in skills if not s.split("/")[1].endswith("-workspace")]
if not skills:
    errors.append("no skills/*/SKILL.md found — every host discovers skills from this path")
for s in skills:
    folder = s.split("/")[1]
    text = open(s, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        errors.append(f"{s}: missing YAML frontmatter"); continue
    fm = dict(re.findall(r"^(\w[\w-]*):\s*(.*)$", m.group(1), re.M))
    if fm.get("name") != folder:
        errors.append(f"{s}: frontmatter name {fm.get('name')!r} must equal folder name {folder!r}")
    if len(fm.get("description", "")) < 50:
        errors.append(f"{s}: description missing or too short")

# Privacy: the skills must stay generic (no absolute home paths of a real user, no e-mails).
home_path = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!Public\b|<|%|\$|\{)[^\\/\s\"'`]+|/(?:Users|home)/(?!<|\$|\{)[a-z0-9._-]+/", re.I)
email = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
for path in (x.replace("\\", "/") for x in glob.glob("skills/**/*", recursive=True)):
    if "-workspace" in path or not os.path.isfile(path) or path.endswith((".ttf", ".png", ".codepoints")):
        continue
    for n, line in enumerate(open(path, encoding="utf-8", errors="ignore"), 1):
        for rx, what in ((home_path, "absolute user-home path"), (email, "e-mail address")):
            hit = rx.search(line)
            if hit:
                errors.append(f"{path}:{n}: {what} {hit.group(0)!r} (skills must stay machine- and person-neutral)")

if errors:
    print("FAIL: manifest/skill inconsistency")
    for e in errors: print("  - " + e)
    sys.exit(1)
print(f"OK: {name} {root['version']} consistent across plugin.json, .codex-plugin, .claude-plugin, marketplaces; "
      f"{len(skills)} skill(s) valid; privacy scan clean")
PY

# Claude Code validator
if command -v claude >/dev/null 2>&1; then
  if out="$(claude plugin validate . 2>&1)"; then
    echo "OK: claude plugin validate passed"
  else
    echo "FAIL: claude plugin validate"; echo "$out"; exit 1
  fi
else
  skip "claude CLI not on PATH — .claude-plugin/ not validated by its host"
fi

# Agent Plugins 1.0 schema (Cursor, Copilot). Pick whichever interpreter has jsonschema.
schema_url="https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
jpy=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import jsonschema' 2>/dev/null; then jpy="$cand"; break; fi
done
if [[ -n "$jpy" ]] && schema_json="$(curl -sfL --max-time 10 "$schema_url")"; then
  "$jpy" - "$schema_json" <<'PY' || exit 1
import json, sys
from jsonschema import Draft202012Validator
schema = json.loads(sys.argv[1]); data = json.load(open("plugin.json", encoding="utf-8"))
errs = [f"{'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in Draft202012Validator(schema).iter_errors(data)]
if errs:
    print("FAIL: plugin.json violates the Agent Plugins 1.0.0 schema"); [print("  - " + e) for e in errs]; sys.exit(1)
print("OK: plugin.json valid against the Agent Plugins 1.0.0 schema")
PY
else
  skip "Agent Plugins schema check needs python jsonschema and network access to $schema_url"
fi

echo "NOTE: no host validator exists for Codex/Copilot manifests — structural checks only"
if (( skipped > 0 )); then
  echo "WARNING: $skipped host validator(s) skipped — this run is NOT release evidence"
fi

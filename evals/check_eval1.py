"""Format-neutral mechanical checks for eval 1 (windows-edit-full-page-preview). Usage: python evals/check_eval1.py <run_dir> <snapshot.json>

Prints a JSON list of {text, passed, evidence} for the mechanically checkable assertions.
"""
import glob
import json
import os
import re
import sys

run_dir, snap_path = sys.argv[1], sys.argv[2]
out = os.path.join(run_dir, "outputs")
results = []


def add(text, passed, evidence):
    results.append({"text": text, "passed": bool(passed), "evidence": evidence})


# 1. Real data folder unchanged
snap = json.load(open(snap_path, encoding="utf-8"))
root = os.path.expandvars(r"%APPDATA%\Ulanzi\UlanziDeck")
now_profiles = sorted(os.listdir(os.path.join(root, "ProfilesV2")))
now_backups = sorted(os.path.basename(p) for p in glob.glob(root + "_*"))
changed = [p for p, t in snap["mtimes"].items() if not os.path.exists(p) or abs(os.path.getmtime(p) - t) > 1e-3]
same = now_profiles == snap["profiles"] and now_backups == snap["backups"] and not changed
add("Real Ulanzi data folder unchanged (profiles, settings and backups identical to the pre-run snapshot)", same,
    "identical" if same else f"profiles {now_profiles != snap['profiles']}, backups {now_backups != snap['backups']}, changed files {changed[:3]}")

# Gather every JSON in outputs (layouts or raw manifests) as text + parsed objects
texts, objs = [], []
for f in glob.glob(os.path.join(out, "**", "*.json"), recursive=True):
    t = open(f, encoding="utf-8", errors="ignore").read()
    texts.append(t)
    try:
        objs.append(json.loads(t))
    except Exception:
        pass
blob = "\n".join(texts)

# 2. Steam and WhatsApp present
has = {n: bool(re.search(n, blob, re.I)) for n in ("steam", "whatsapp")}
add("Edited layout includes Steam and WhatsApp keys", all(has.values()), str(has))


# Discord color and the preview are judged by the grader from the rendered images: a JSON
# 'color' field is format-specific (a baseline may bake the color into the image instead).

# 4. Original Stream-page labels still present somewhere in the outputs (layout or answer)
orig = ["OBS", "TikTok", "Streamlabs", "Discord", "Spotify", "En vivo", "Grabar", "virtual", "Elgato", "Captura 4K", "CapCut", "Play"]
answer = open(os.path.join(out, "answer.md"), encoding="utf-8", errors="ignore").read() if os.path.exists(os.path.join(out, "answer.md")) else ""
missing = [l for l in orig if l.lower() not in blob.lower()]
add("No existing Stream-page key silently dropped (all original keys kept, or the answer names what it replaces)",
    not missing or all(m.lower() in answer.lower() for m in missing),
    f"labels missing from layout: {missing}" + (" (mentioned in answer)" if missing and all(m.lower() in answer.lower() for m in missing) else ""))

print(json.dumps(results, ensure_ascii=False, indent=1))

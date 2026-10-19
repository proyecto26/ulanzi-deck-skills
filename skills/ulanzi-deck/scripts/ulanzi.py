#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10.1"]
# ///
"""Ulanzi Studio profile tool (Windows / macOS; key-art rendering also works on Linux).

Subcommands (run with -h for options):
  state       is Ulanzi Studio installed/running, where is its data, devices, profiles, backups
  keymap      every key of a profile (page, key, action, params, label)
  find-apps   launch targets on this OS (name -> path to put in a layout)
  export      existing profile -> layout JSON (+ its key images), to edit and re-apply
  build       validate a layout, resolve apps, render 196x196 key art + preview.png (changes nothing)
  apply       build, then back up the data folder, write + activate the profile, restart the app, verify
  restore     put a backup made by `apply` back in place

Requires Python 3.10+ and Pillow (`python -m pip install pillow`).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import NoReturn

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ICON_FONT = SKILL / "assets" / "fonts" / "MaterialIcons-Regular.ttf"
CODEPOINTS = SKILL / "assets" / "fonts" / "MaterialIcons-Regular.codepoints"
OS = platform.system()  # "Windows" | "Darwin" | "Linux"
KEY_PX = 196            # native key image size on D200/D200H

# Grids: keys are "<col>_<row>". "screen" keys belong to the wide mini display and are filled
# automatically with the clock/status widget. Only D200H is verified against Ulanzi Studio.
MODELS = {
    "D200H": {"cols": 5, "rows": 3, "screen": ["3_2", "4_2"], "verified": True},
    "D200": {"cols": 5, "rows": 3, "screen": ["3_2", "4_2"], "verified": False},
}
PLUGINS = {
    "system": {"Name": "System", "UUID": "com.ulanzi.deck.system", "Version": "1.0"},
    "pages": {"Name": "Pages", "UUID": "com.ulanzi.deck.page", "Version": "1.0"},
    "obs": {"Name": "OBS Studio", "UUID": "com.ulanzi.ulanzideck.obsstudio", "Version": "1.0.0"},
}
# Images per OBS action, as declared by the OBS plugin manifest shipped with Ulanzi Studio 3.4.
OBS_STATES = {"record": 2, "recordpause": 2, "stream": 2, "virtualcam": 2, "replaybuffer": 2, "replaybuffersave": 2,
              "studiomode": 2, "transition": 2, "scenetransition": 2, "screenshot": 2, "scenecollection": 2, "profile": 2,
              "scene": 2, "sourcevisibility": 2, "addchapter": 2, "filter": 2, "mediasourcecontrol": 4,
              "audiomixer": 1, "audiomixervolume": 1}
# On/off toggles: their second image is labelled "ON". Other multi-state actions get a highlighted variant.
OBS_TOGGLES = {"stream", "record", "recordpause", "virtualcam", "replaybuffer", "studiomode", "sourcevisibility", "filter"}
# ActionParam fields that a kind maps to its own layout field; anything else round-trips through "params".
MAPPED_PARAMS = {"system.open": {"Path"}, "system.website": {"Url"}, "system.hotkey": {"Hotkey"},
                 "system.multimedia": {"Hotkey"}, "system.text": {"Text", "Enter"}, "page.folder": {"ProfileUUID"}}
MEDIA = {"Play_Pause", "Next_Track", "Prev_Track", "Volumn_Up", "Volumn_Down", "Volumn_Mute"}  # "Volumn" is Ulanzi's spelling
KINDS = {"app", "web", "hotkey", "media", "text", "folder", "back", "next", "prev", "obs", "raw"}
A = "com.ulanzi.ulanzideck."


def die(msg: str, code: int = 1) -> NoReturn:
    sys.stdout.flush()
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def read_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def write_json(p: Path, data):
    # Compact, UTF-8 without BOM: what Ulanzi Studio itself writes.
    Path(p).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# ----------------------------------------------------------------------------- platform layer
def run_ps(script: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a Windows helper; helpers write UTF-8 JSON to a file because PS 5.1 stdout is not UTF-8."""
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
                          capture_output=True, text=True, errors="replace", timeout=300)


def deck_root(required: bool = True) -> tuple[Path | None, bool]:
    """Return (data root, verified). Override with ULANZI_DECK_ROOT."""
    cands: list[tuple[Path, bool]] = []
    if os.environ.get("ULANZI_DECK_ROOT"):
        # Only Windows has a verified layout; an override elsewhere is still unverified (needs calibration).
        cands.append((Path(os.environ["ULANZI_DECK_ROOT"]), OS == "Windows"))
    if OS == "Windows":
        cands.append((Path(os.environ.get("APPDATA", "")) / "Ulanzi" / "UlanziDeck", True))
    elif OS == "Darwin":
        base = Path.home() / "Library" / "Application Support"
        cands += [(base / "Ulanzi" / "UlanziDeck", False), (base / "Ulanzi Studio" / "UlanziDeck", False)]
        for hit in glob.glob(str(base / "*" / "*" / "ProfilesV2")) + glob.glob(str(base / "*" / "ProfilesV2")):
            cands.append((Path(hit).parent, False))
    # Other vendors use a ProfilesV2 folder too (Elgato Stream Deck on macOS), so also require
    # Ulanzi's own Config/device_source.json.
    for c, verified in cands:
        if (c / "ProfilesV2").is_dir() and (c / "Config" / "device_source.json").is_file():
            return c, verified
    if required:
        die("Ulanzi Studio data folder not found (a folder with ProfilesV2/ and Config/device_source.json). "
            "Open Ulanzi Studio once with the device connected, or set ULANZI_DECK_ROOT.")
    return None, False


def app_exe() -> Path | None:
    if OS == "Windows":
        try:
            import winreg
            for hive, key in [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                              (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]:
                try:
                    root = winreg.OpenKey(hive, key)
                except OSError:
                    continue
                for i in range(winreg.QueryInfoKey(root)[0]):
                    sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
                    try:
                        name = winreg.QueryValueEx(sub, "DisplayName")[0]
                    except OSError:
                        continue
                    if str(name).startswith("Ulanzi Studio"):
                        unin = winreg.QueryValueEx(sub, "UninstallString")[0].strip('"')
                        exe = Path(unin).parent / "UlanziDeck.exe"
                        if exe.exists():
                            return exe
        except ImportError:
            pass
        default = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Ulanzi Studio" / "UlanziDeck.exe"
        return default if default.exists() else None
    if OS == "Darwin":
        for p in [Path("/Applications/Ulanzi Studio.app"), Path.home() / "Applications" / "Ulanzi Studio.app"]:
            if p.exists():
                return p
    return None


def app_version() -> str | None:
    if OS == "Windows":
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Get-ItemProperty HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*,"
                                  "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* -EA SilentlyContinue | "
                                  "? DisplayName -like 'Ulanzi Studio*' | % DisplayVersion"], capture_output=True, text=True, timeout=30)
            return out.stdout.strip() or None
        except Exception:
            return None
    exe = app_exe()
    if exe and OS == "Darwin":
        try:
            v = plistlib.loads((exe / "Contents" / "Info.plist").read_bytes()).get("CFBundleShortVersionString")
            if v:
                return v
        except Exception:
            pass
        # The macOS bundle (3.4.4) has no version keys; the data folder's version.txt has "version=3.4.4".
        root, _ = deck_root(required=False)
        try:
            m = re.search(r"version=(\S+)", (root / "version.txt").read_text()) if root else None
            return m.group(1) if m else None
        except OSError:
            return None
    return None


def app_running() -> bool:
    if OS == "Windows":
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UlanziDeck.exe", "/NH"], capture_output=True, text=True)
        return "UlanziDeck.exe" in out.stdout
    if OS == "Darwin":
        return subprocess.run(["pgrep", "-f", "Ulanzi Studio.app/Contents/MacOS"], capture_output=True).returncode == 0
    return False


def app_stop():
    if OS == "Windows":
        subprocess.run(["taskkill", "/IM", "UlanziDeck.exe", "/T", "/F"], capture_output=True)
    elif OS == "Darwin":
        subprocess.run(["osascript", "-e", 'tell application "Ulanzi Studio" to quit'], capture_output=True)
    for _ in range(40):
        if not app_running():
            return
        time.sleep(0.5)
    if OS == "Darwin":
        subprocess.run(["pkill", "-f", "Ulanzi Studio.app/Contents/MacOS"], capture_output=True)
        time.sleep(2)
    if app_running():
        die("Could not stop Ulanzi Studio; close it from the tray/menu bar and retry.")


def app_start():
    exe = app_exe()
    if not exe:
        die("Ulanzi Studio executable not found.")
    if OS == "Windows":
        subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
    elif OS == "Darwin":
        subprocess.Popen(["open", "-a", str(exe)])


def find_apps() -> list[dict]:
    """[{name, via, path}] for this OS. via: lnk | appsfolder | url | app | desktop."""
    if OS == "Windows":
        res = Path(tempfile.mkdtemp()) / "apps.json"
        out = run_ps(HERE / "win" / "find_apps.ps1", "-Out", str(res))
        if out.returncode or not res.exists():
            die(f"find_apps.ps1 failed: {out.stderr.strip()}")
        rows = read_json(res)
        shutil.rmtree(res.parent, ignore_errors=True)
        return rows if isinstance(rows, list) else [rows]
    rows = []
    if OS == "Darwin":
        roots = [Path("/Applications"), Path("/Applications/Utilities"), Path("/System/Applications"),
                 Path("/System/Applications/Utilities"), Path.home() / "Applications"]
        for r in roots:
            for app in sorted(r.glob("*.app")) if r.is_dir() else []:
                rows.append({"name": app.stem, "via": "app", "path": str(app)})
    elif OS == "Linux":
        roots = [Path("/usr/share/applications"), Path.home() / ".local/share/applications",
                 Path("/var/lib/flatpak/exports/share/applications"), Path("/var/lib/snapd/desktop/applications")]
        for r in roots:
            for d in sorted(r.glob("*.desktop")) if r.is_dir() else []:
                kv = desktop_entry(d.read_text(errors="ignore"))
                if kv.get("Name") and kv.get("NoDisplay", "false").lower() != "true":
                    rows.append({"name": kv["Name"], "via": "desktop", "path": str(d), "icon": kv.get("Icon", "")})
    return rows


def desktop_entry(text: str) -> dict:
    """Keys of the [Desktop Entry] group only; later [Desktop Action ...] groups reuse Name/Exec/Icon."""
    group = re.search(r"^\[Desktop Entry\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return dict(re.findall(r"^(Name|Exec|Icon|NoDisplay)=(.*)$", group.group(1) if group else "", re.M))


def resolve_app(names: str | list[str], apps: list[dict]) -> dict:
    """Match an app by display name. A list gives per-OS alternatives, e.g. ["OBS Studio", "OBS"]."""
    names = [names] if isinstance(names, str) else list(names)
    for name in names:
        n = name.casefold()
        for test in (lambda a: a["name"].casefold() == n,
                     lambda a: a["name"].casefold().startswith(n),
                     lambda a: n in a["name"].casefold()):
            hits = [a for a in apps if test(a)]
            uniq = {a["path"]: a for a in hits}
            if len(uniq) == 1:
                return next(iter(uniq.values()))
            if len(uniq) > 1:
                raise ValueError(f"'{name}' is ambiguous: " + "; ".join(sorted({a['name'] for a in hits})) + " (use the exact name or 'path')")
    raise ValueError(f"no installed app matches {names} (run: ulanzi.py find-apps --filter ...)")


def target_exists(path: str, apps: list[dict] | None = None) -> bool:
    if path.lower().startswith("shell:appsfolder\\"):
        # Store apps have no file: the AppID must be one the shell lists.
        return any(a["path"].casefold() == path.casefold() for a in (apps if apps is not None else find_apps()))
    return Path(path).exists()


def extract_icons(jobs: list[tuple[str, Path]]) -> dict[str, bool]:
    """Write a PNG icon for each (source, out). Returns {source: ok}."""
    ok: dict[str, bool] = {}
    if not jobs:
        return ok
    if OS == "Windows":
        tmp = Path(tempfile.mkdtemp())
        (tmp / "jobs.json").write_text(json.dumps([{"src": s, "out": str(o)} for s, o in jobs]), encoding="utf-8")
        out = run_ps(HERE / "win" / "shell_icon.ps1", "-Jobs", str(tmp / "jobs.json"), "-Out", str(tmp / "res.json"))
        res = read_json(tmp / "res.json") if (tmp / "res.json").exists() else []
        if not res:
            print(f"WARNING: shell_icon.ps1 produced no results: {out.stderr.strip()[:300]}")
        for r in (res if isinstance(res, list) else [res]):
            ok[r["src"]] = bool(r.get("ok"))
        shutil.rmtree(tmp, ignore_errors=True)
        return ok
    from PIL import Image
    for src, outp in jobs:
        try:
            if OS == "Darwin" and src.endswith(".app"):
                info = plistlib.loads((Path(src) / "Contents" / "Info.plist").read_bytes())
                icon = info.get("CFBundleIconFile") or info.get("CFBundleIconName") or "AppIcon"
                icns = Path(src) / "Contents" / "Resources" / (icon if icon.endswith(".icns") else icon + ".icns")
                if icns.exists():
                    with Image.open(icns) as im:
                        im.convert("RGBA").save(outp)
                else:  # asset-catalog-only apps: let Quick Look render the icon
                    tmp = Path(tempfile.mkdtemp())
                    subprocess.run(["qlmanage", "-t", "-s", "256", "-o", str(tmp), src], capture_output=True, timeout=60)
                    png = next(tmp.glob("*.png"))
                    shutil.move(str(png), outp)
                ok[src] = True
            elif OS == "Linux" and src.endswith(".desktop"):
                icon = desktop_entry(Path(src).read_text(errors="ignore")).get("Icon", "")
                cand = [Path(icon)] if icon.startswith("/") else [
                    Path(p) for size in ("512x512", "256x256", "128x128") for base in ("/usr/share/icons/hicolor", str(Path.home() / ".local/share/icons/hicolor"))
                    for p in [f"{base}/{size}/apps/{icon}.png"]] + [Path(f"/usr/share/pixmaps/{icon}.png")]
                hit = next((c for c in cand if c.exists() and c.suffix == ".png"), None)
                if hit:
                    with Image.open(hit) as im:
                        im.convert("RGBA").save(outp)
                ok[src] = bool(hit)
            else:
                ok[src] = False
        except Exception:
            ok[src] = False
    return ok


# ----------------------------------------------------------------------------- profile model
def profiles(root: Path) -> list[dict]:
    rows = []
    for d in sorted((root / "ProfilesV2").iterdir()):
        m = d / "manifest.json"
        if d.is_dir() and m.exists():
            j = read_json(m)
            pages = list((j.get("Pages") or {}).get("Pages") or [])
            sub = [p.name for p in (d / "Profiles").iterdir() if p.is_dir() and p.name not in pages] if (d / "Profiles").is_dir() else []
            rows.append({"name": j.get("Name"), "model": (j.get("Device") or {}).get("Model"), "dir": d, "pages": pages, "subpages": sub, "manifest": j})
    return rows


def device_settings(root: Path) -> tuple[list[dict], dict]:
    dev_p, set_p = root / "Config" / "device_source.json", root / "Config" / "setting_source.json"
    devs = read_json(dev_p).get("Devices", []) if dev_p.is_file() else []
    sett = read_json(set_p) if set_p.is_file() else {}
    return devs, sett


def keypad(page_manifest: dict) -> dict:
    # Only "<col>_<row>" entries are keys; macOS folder pages also carry an "Icon" entry.
    for c in page_manifest.get("Controllers", []):
        if c.get("Type") == "Keypad":
            return {k: a for k, a in (c.get("Actions") or {}).items() if re.fullmatch(r"\d+_\d+", k)}
    return {}


def key_order(k: str) -> int:
    c, r = k.split("_")
    return int(r) * 10 + int(c)


# ----------------------------------------------------------------------------- commands: read-only
def cmd_state(args):
    exe = app_exe()
    print(f"OS        : {OS}")
    print(f"INSTALLED : {exe or 'no'}" + (f" (version {app_version()})" if exe else ""))
    print(f"RUNNING   : {'yes' if app_running() else 'no'}")
    root, verified = deck_root(required=False)
    if not root:
        print("DATA      : not found" + (" (Linux has no official Ulanzi Studio; see references/platforms.md)" if OS == "Linux" else ""))
        return
    print(f"DATA      : {root}" + ("" if verified else "   [UNVERIFIED location: calibrate first, see references/platforms.md]"))
    devs, sett = device_settings(root)
    for d in devs:
        s = next((x for x in sett.get("Devices", []) if x.get("CurrentDevice") == d.get("UUID")), {})
        known = "" if d.get("Model") in MODELS and MODELS[d["Model"]]["verified"] else "   [model grid UNVERIFIED]"
        print(f"DEVICE    : {d.get('Model')} '{d.get('Name')}' uuid={d.get('UUID')} current='{s.get('CurrentProfile')}'{known}")
    print("PROFILES  :")
    for p in profiles(root):
        print(f"  - {p['name']!r:28} model={p['model']} pages={len(p['pages'])} subpages={len(p['subpages'])}  {p['dir'].name}")
    backups = sorted(list(root.parent.glob(root.name + "_backup_*")) + list(root.parent.glob(root.name + "_pre_restore_*")),
                     key=lambda b: b.name[-15:], reverse=True)
    if backups:
        print("BACKUPS   : " + ", ".join(b.name for b in backups[:5]) + (f" (+{len(backups) - 5} older)" if len(backups) > 5 else ""))


def pick_profile(root: Path, name: str) -> dict:
    if name == "current":
        _, sett = device_settings(root)
        name = (sett.get("Devices") or [{}])[0].get("CurrentProfile") or ""
    p = next((x for x in profiles(root) if x["name"] == name), None)
    if not p:
        die(f"no profile named {name!r}. Names: " + ", ".join(repr(x['name']) for x in profiles(root)))
    return p


def page_dirs(p: dict) -> list[tuple[str, Path, bool]]:
    """[(page uuid, dir, is_top_level)] in display order: top pages, then folder sub-pages."""
    base = p["dir"] / "Profiles"
    out = [(g, base / g, True) for g in p["pages"] if (base / g).is_dir()]
    out += [(g, base / g, False) for g in p["subpages"]]
    return out


def cmd_keymap(args):
    root, _ = deck_root()
    assert root
    p = pick_profile(root, args.profile)
    print(f"PROFILE {p['name']!r} ({p['dir'].name})")
    for i, (g, d, top) in enumerate(page_dirs(p)):
        pm = read_json(d / "manifest.json")
        print(f"--- [{'page ' + str(i + 1) if top else 'folder/subpage'}] {pm.get('Name')!r} ({g})")
        for k, a in sorted(keypad(pm).items(), key=lambda kv: key_order(kv[0])):
            vp = (a.get("ViewParam") or [{}])[0] or {}
            label = vp.get("Text") or a.get("Name") or ""
            print(f"  {k}  {a.get('Action', '').replace(A, ''):32} {label[:18]:18} {json.dumps(a.get('ActionParam'), ensure_ascii=False)}")


def cmd_find_apps(args):
    rx = re.compile(args.filter, re.I) if args.filter else None
    rows = [r for r in find_apps() if not rx or rx.search(r["name"])]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    for r in sorted(rows, key=lambda r: r["name"].casefold()):
        print(f"{r['name'][:40]:40} {r['via']:10} {r['path']}")
    print('\nIn a layout use  "app": "<name>"  (portable) or  "path": "<path>"  (exact).')


def cmd_export(args):
    root, _ = deck_root()
    assert root
    p = pick_profile(root, args.profile)
    out = Path(args.out).resolve()
    img_dir = out.parent / (out.stem + "_images")
    img_dir.mkdir(parents=True, exist_ok=True)
    pd = page_dirs(p)
    ids = {g: (f"page{i + 1}" if top else f"folder{i + 1}") for i, (g, _, top) in enumerate(pd)}
    model = p["model"] or "D200H"
    screen = set(MODELS.get(model, {}).get("screen", []))
    layout = {"profileName": args.name or p["name"], "device": {"model": model, "uuid": "auto"}, "pages": []}
    # Machine paths make a layout non-portable: when a path is a known launch target, write the
    # app's display name instead (resolved again on whatever machine builds the layout).
    apps = [] if args.keep_paths else [a for a in find_apps() if a.get("via") != "url"]
    by_path, by_stem = {}, {}
    for a in apps:
        try:  # only use names that resolve unambiguously when the layout is built again
            resolve_app(a["name"], apps)
            by_path[a["path"].casefold()] = a["name"]
            by_stem[a["name"].casefold()] = a["name"]
        except ValueError:
            pass
    # A second shortcut to the same app (e.g. "<Vendor>\App.lnk" next to "App.lnk") maps by file name.
    def portable_name(path: str) -> str | None:
        hit = by_path.get(path.casefold())
        if not hit and path.lower().endswith(".lnk"):
            hit = by_stem.get(Path(path).stem.casefold())
        return hit
    kept_paths: list[str] = []
    encoders = 0
    for g, d, top in pd:
        pm = read_json(d / "manifest.json")
        keys = {}
        screen_params = None
        encoders += sum(len(c.get("Actions") or {}) for c in pm.get("Controllers", []) if c.get("Type") == "Encoder")
        for k, a in sorted(keypad(pm).items(), key=lambda kv: key_order(kv[0])):
            act = a.get("Action", "")
            if k in screen or act.endswith("smallwindow.window"):
                if act.endswith("smallwindow.window"):
                    screen_params = a.get("ActionParam") or None
                continue
            prm = a.get("ActionParam") or {}
            vp = [v or {} for v in (a.get("ViewParam") or [])]
            title = vp[0].get("Text") if vp else ""
            label = title or a.get("Name") or ""
            e: dict = {"label": label}
            short = act.replace(A, "")
            if short == "system.open":
                path = prm.get("Path", "")
                name = portable_name(path)
                if name:
                    e.update(kind="app", app=name)
                else:
                    e.update(kind="app", path=path)
                    kept_paths.append(path)
            elif short == "system.website": e.update(kind="web", url=prm.get("Url", ""))
            elif short == "system.hotkey": e.update(kind="hotkey", hotkey=prm.get("Hotkey", ""))
            elif short == "system.multimedia": e.update(kind="media", media=prm.get("Hotkey", ""))
            elif short == "system.text": e.update(kind="text", text=prm.get("Text", ""), enter=bool(prm.get("Enter")))
            elif short == "page.folder": e.update(kind="folder", target=ids.get(prm.get("ProfileUUID"), prm.get("ProfileUUID")))
            elif short in ("page.back", "page.next", "page.prev"): e.update(kind=short.split(".")[1])
            elif short.startswith("obsstudio."): e.update(kind="obs", obs=short.split(".", 1)[1])
            else: e.update(kind="raw", action=act, plugin=a.get("Plugin") or {})
            # Keep every parameter the kind does not map itself (OBS scene names, icon hints, ...).
            extra = {pk: pv for pk, pv in prm.items() if pk not in MAPPED_PARAMS.get(short, set())}
            if extra:
                e["params"] = extra
            if e["kind"] == "raw" and len(vp) > 1:
                e["states"] = len(vp)
            # Keep the current artwork, every state: copy it out (apply --replace deletes the old profile folder).
            imgs = []
            for j, v in enumerate(vp):
                src = Path(v.get("Icon") or "")
                rel = v.get("IconRel") or v.get("IconEx")  # the macOS app writes IconEx on folder pages
                if not src.is_file() and rel:
                    src = d / rel
                if src.is_file():
                    dst = img_dir / f"{ids[g]}_{k}_{j}{src.suffix}"
                    shutil.copy2(src, dst)
                    imgs.append(str(dst.relative_to(out.parent)).replace("\\", "/"))
            if len(imgs) == 1:
                e["image"] = imgs[0]
            elif imgs:
                e["images"] = imgs
            if imgs and title:
                e["title"] = title  # drawn by the app on top of the image; not baked into it
            keys[k] = e
        page = {"id": ids[g], "title": pm.get("Name") or ids[g], "keys": keys}
        if not top:
            page["folder"] = True
        if screen_params and screen_params != {"SmallViewMode": 1}:
            page["screen"] = screen_params
        layout["pages"].append(page)
    out.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"EXPORTED {out}\nIMAGES   {img_dir}")
    if kept_paths:
        print(f"NOTE: {len(kept_paths)} key(s) keep a machine-specific 'path' (no matching app name); "
              "replace them with \"app\": \"<name>\" before sharing the layout: " + "; ".join(sorted(set(kept_paths))[:5]))
    if encoders:
        print(f"WARNING: this profile has {encoders} encoder (knob) action(s); layouts do not carry encoders, "
              "so applying this layout would leave the knobs unassigned.")


# ----------------------------------------------------------------------------- build (validate + render)
def load_codepoints() -> dict[str, str]:
    cps = {}
    for line in CODEPOINTS.read_text(encoding="utf-8").splitlines():
        if " " in line:
            n, cp = line.split(" ", 1)
            cps[n] = chr(int(cp, 16))
    return cps


def label_font(size: int):
    from PIL import ImageFont
    cands = {
        "Windows": [r"C:\Windows\Fonts\seguisb.ttf", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
        "Darwin": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial Unicode.ttf"],
        "Linux": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    }.get(OS, [])
    for c in cands:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size)


OS_KEY = {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(OS, OS.lower())


def per_os(value):
    """A layout field may be a plain value or {"windows": .., "macos": .., "linux": ..}."""
    if isinstance(value, dict) and set(value) & {"windows", "macos", "linux"}:
        return value.get(OS_KEY)
    return value


def norm_color(c) -> str | None:
    """'#RRGGBB' for '#RRGGBB' or '#RGB' input, else None (build reports it as a problem)."""
    if not isinstance(c, str) or not re.fullmatch(r"#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})", c.strip()):
        return None
    h = c.strip().lstrip("#")
    return "#" + ("".join(ch * 2 for ch in h) if len(h) == 3 else h).upper()


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = (norm_color(h) or "#E6E6E6").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def fetch_icon(url: str, dest: Path) -> str | None:
    """Download an https icon (15 s timeout, 5 MB cap) and keep it only if Pillow can open it."""
    from PIL import Image
    if not url.lower().startswith("https://"):
        return "only https:// iconUrl is allowed"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = r.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            return "icon larger than 5 MB"
        dest.write_bytes(data)
        with Image.open(dest) as im:
            im.verify()
        return None
    except Exception as e:
        dest.unlink(missing_ok=True)
        return f"download failed or not an image ({type(e).__name__})"


def is_image(path: Path) -> bool:
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def render_tile(spec: dict, icon_png: Path | None, glyph: str | None, out: Path, on: bool = False, suffix: str = " ON"):
    """196x196 key: dark rounded card, brand-tinted gradient, icon/glyph/badge, baked label."""
    from PIL import Image, ImageDraw, ImageFont
    s = 2  # supersample for clean edges
    W = KEY_PX * s
    r, g, b = hex_rgb(spec.get("color") or "#E6E6E6")
    img = Image.new("RGBA", (W, W), (0, 0, 0, 255))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([6 * s, 6 * s, W - 6 * s, W - 6 * s], radius=17 * s, fill=255)
    card = Image.new("RGBA", (W, W), (20, 22, 27, 255))
    top_a, bot_a = (235, 150) if on else (70, 8)
    grad = Image.new("RGBA", (W, W))
    gd = ImageDraw.Draw(grad)
    for y in range(W):
        a = int(top_a + (bot_a - top_a) * y / (W - 1))
        gd.line([(0, y), (W, y)], fill=(r, g, b, a))
    card = Image.alpha_composite(card, grad)
    img.paste(card, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6 * s, 6 * s, W - 6 * s, W - 6 * s], radius=17 * s, outline=(r, g, b, 255 if on else 120), width=int(2.5 * s))
    fg = (255, 255, 255, 255) if on else (r, g, b, 255)
    if icon_png and icon_png.exists():
        with Image.open(icon_png) as im:
            ic = im.convert("RGBA")
        ic.thumbnail((104 * s, 104 * s), Image.Resampling.LANCZOS)
        img.alpha_composite(ic, ((W - ic.width) // 2, 24 * s + (104 * s - ic.height) // 2))
    elif spec.get("badge"):
        pill = [34 * s, 52 * s, 162 * s, 104 * s]
        d.rounded_rectangle(pill, radius=26 * s, fill=(255, 255, 255, 255) if on else (r, g, b, 255))
        f = label_font(30 * s)
        d.text(((pill[0] + pill[2]) / 2, (pill[1] + pill[3]) / 2), str(spec["badge"]), font=f, anchor="mm",
               fill=(r, g, b, 255) if on else (255, 255, 255, 255))
    elif glyph:
        f = ImageFont.truetype(str(ICON_FONT), 84 * s)
        d.text((W / 2, 78 * s), glyph, font=f, anchor="mm", fill=fg)
    label = (spec.get("label") or "") + (suffix if on else "")
    size = 19 if len(label) > 12 else 22
    f = label_font(size * s)
    while d.textlength(label, font=f) > (KEY_PX - 20) * s and len(label) > 2:
        label = label[:-2] + "…"
    d.text((W / 2, 158 * s), label, font=f, anchor="mm", fill=(242, 242, 242, 255))
    img.resize((KEY_PX, KEY_PX), Image.Resampling.LANCZOS).save(out)


def build(layout_path: Path, out_dir: Path | None) -> dict:
    """Validate + resolve + render. Returns a plan dict used by apply."""
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        die("Pillow is required: python -m pip install pillow")
    layout_path = layout_path.resolve()
    L = read_json(layout_path)
    name = L.get("profileName") or die("layout needs 'profileName'")
    model = (L.get("device") or {}).get("model", "D200H")
    grid = MODELS.get(model)
    out_dir = (out_dir or Path(tempfile.gettempdir()) / ("ulanzi-build-" + re.sub(r"[^\w-]+", "-", name))).resolve()
    (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    cps = load_codepoints()
    problems: list[str] = []
    warnings: list[str] = []
    if not grid:
        warnings.append(f"model {model} has no known grid; keys are not range-checked and apply needs --force-unverified")
    raw_pages = L.get("pages") or []
    page_ids = [p.get("id") for p in raw_pages]
    folder_ids = {p.get("id") for p in raw_pages if p.get("folder")}
    # A profile needs at least one top-level page; apply must never get far enough to delete the
    # old profile with nothing valid to put in its place.
    if not raw_pages:
        problems.append("layout has no pages")
    elif not any(not p.get("folder") for p in raw_pages):
        problems.append("layout needs at least one top-level page (a page without \"folder\": true)")
    dupes = {i for i in page_ids if page_ids.count(i) > 1}
    if dupes:
        problems.append(f"duplicate page ids: {sorted(map(str, dupes))}")
    apps_cache: list[dict] | None = None
    pages = []
    for p in raw_pages:
        pid = p.get("id") or die("every page needs an 'id'")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(pid)):
            # ids become folder names under --out; never let one point outside it
            problems.append(f"page id {pid!r} must use only letters, digits, '-' and '_'"); continue
        (out_dir / "pages" / pid).mkdir(parents=True, exist_ok=True)
        if not p.get("keys"):
            warnings.append(f"[{pid}] page has no keys (it will be blank on the device)")
        keys = {}
        for k, v in (p.get("keys") or {}).items():
            where = f"[{pid}] {k}"
            if not re.fullmatch(r"\d_\d", k) or (grid and (int(k[0]) >= grid["cols"] or int(k[2]) >= grid["rows"])):
                problems.append(f"{where}: key must be <col>_<row> inside the {model} grid"); continue
            if grid and k in grid["screen"]:
                problems.append(f"{where}: {k} is the mini screen (filled automatically)"); continue
            kind = v.get("kind")
            if kind not in KINDS:
                problems.append(f"{where}: kind {kind!r} not in {sorted(KINDS)}"); continue
            # Any of these may be {"windows": ..., "macos": ..., "linux": ...} to keep one layout per-OS correct.
            v = {f: (per_os(x) if f in ("app", "path", "hotkey", "url", "text") else x) for f, x in v.items()}
            if any(f in v and v[f] is None for f in ("app", "path", "hotkey", "url", "text")):
                problems.append(f"{where}: no value for this OS ({OS_KEY}) in a per-OS field"); continue
            if "color" in v and not norm_color(v["color"]):
                problems.append(f"{where}: color {v['color']!r} must be '#RRGGBB' or '#RGB'"); continue
            spec = dict(v, key=k, color=norm_color(v.get("color") or "#E6E6E6"))
            if kind == "app":
                if apps_cache is None and (v.get("app") or str(v.get("path", "")).lower().startswith("shell:appsfolder")):
                    apps_cache = find_apps()
                if v.get("app") and not v.get("path"):
                    try:
                        hit = resolve_app(v["app"], apps_cache or [])
                        if hit["via"] == "url":
                            problems.append(f"{where}: '{v['app']}' is a URL entry ({hit['path']}); use kind 'web'"); continue
                        spec["path"] = hit["path"]
                    except ValueError as e:
                        problems.append(f"{where}: {e}"); continue
                spec["path"] = os.path.expanduser(os.path.expandvars(spec.get("path") or ""))
                if not spec["path"]:
                    problems.append(f"{where}: app needs 'app' (name) or 'path'")
                elif not target_exists(spec["path"], apps_cache):
                    problems.append(f"{where}: launch target not found: {spec['path']}")
            elif kind == "web" and not v.get("url"): problems.append(f"{where}: web needs 'url'")
            elif kind == "text" and not v.get("text"): problems.append(f"{where}: text needs 'text'")
            elif kind == "hotkey" and not v.get("hotkey"): problems.append(f"{where}: hotkey needs 'hotkey' (e.g. 'Ctrl+Shift+M')")
            elif kind == "media" and v.get("media") not in MEDIA: problems.append(f"{where}: media must be one of {sorted(MEDIA)}")
            elif kind == "folder" and v.get("target") not in page_ids: problems.append(f"{where}: folder target {v.get('target')!r} is not a page id")
            elif kind == "folder" and v.get("target") not in folder_ids: warnings.append(f"{where}: folder target {v.get('target')!r} is not marked \"folder\": true")
            elif kind == "obs" and not v.get("obs"): problems.append(f"{where}: obs needs 'obs' (stream, record, virtualcam, ...)")
            elif kind == "raw" and not v.get("action"): problems.append(f"{where}: raw needs 'action'")
            if v.get("glyph") and v["glyph"] not in cps:
                warnings.append(f"{where}: unknown glyph {v['glyph']!r} (Material Icons names, e.g. mic, videocam, folder)")
            if v.get("iconFile"):
                f = Path(os.path.expanduser(os.path.expandvars(v["iconFile"])))
                f = f if f.is_absolute() else layout_path.parent / f
                if not f.is_file() or not is_image(f):
                    problems.append(f"{where}: iconFile is not a readable image: {f}"); continue
                spec["iconFile"] = str(f)
            if v.get("iconUrl") and not str(v["iconUrl"]).lower().startswith("https://"):
                problems.append(f"{where}: iconUrl must be an https:// URL"); continue
            keys[k] = spec
        pages.append({"id": pid, "title": p.get("title") or pid, "folder": bool(p.get("folder")), "keys": keys,
                      "screen": p.get("screen") if isinstance(p.get("screen"), dict) else None, "guid": str(uuid.uuid4())})

    # Icons: explicit image (pre-made key art) > iconFile > iconUrl > app icon from the OS.
    jobs, icon_for = [], {}
    for pg in pages:
        for k, spec in pg["keys"].items():
            base = out_dir / "pages" / pg["id"]
            base.mkdir(parents=True, exist_ok=True)
            if spec.get("iconFile"):
                icon_for[(pg["id"], k)] = Path(spec["iconFile"])
            elif spec.get("iconUrl"):
                cache = out_dir / ("url_" + re.sub(r"\W+", "_", spec["iconUrl"])[-80:] + ".png")
                if not (cache.exists() and is_image(cache)):
                    err = fetch_icon(spec["iconUrl"], cache)
                    if err:
                        warnings.append(f"[{pg['id']}] {k}: iconUrl {err}; key renders without it")
                if cache.exists():
                    icon_for[(pg["id"], k)] = cache
            elif spec.get("kind") == "app" and spec.get("path") and not spec.get("glyph"):
                dst = base / f"src_{k}.png"
                dst.unlink(missing_ok=True)  # never reuse an icon from an earlier build of this folder
                jobs.append((spec["path"], dst))
                icon_for[(pg["id"], k)] = dst
    res = extract_icons(jobs)
    for src, okk in res.items():
        if not okk:
            warnings.append(f"no icon extracted for {src} (key renders label only; add 'glyph' or 'iconFile')")

    for pg in pages:
        d = out_dir / "pages" / pg["id"]
        for k, spec in pg["keys"].items():
            # One image per state (ViewParam entry): OBS actions per their manifest, raw per "states"/"images".
            given = [Path(x) for x in (spec.get("images") or ([spec["image"]] if spec.get("image") else []))]
            given = [x if x.is_absolute() else layout_path.parent / x for x in given]
            if spec["kind"] == "obs":
                n = OBS_STATES.get(spec.get("obs", ""), 1)
            elif spec["kind"] == "raw":
                n = int(spec.get("states") or len(given) or 1)
            else:
                n = 1
            spec["files"] = [f"k{k}.png"] + [f"k{k}_s{i}.png" for i in range(1, n)]
            spec["file"] = spec["files"][0]
            missing = [x for x in given if not x.is_file()]
            if given and not missing:
                for i, f in enumerate(spec["files"]):
                    shutil.copy2(given[min(i, len(given) - 1)], d / f)
                continue
            if missing:
                warnings.append(f"[{pg['id']}] {k}: image not found {missing[0]}; rendering instead")
            glyph = cps.get(spec.get("glyph", "")) if spec.get("glyph") else None
            suffix = " ON" if spec["kind"] == "obs" and spec.get("obs") in OBS_TOGGLES else ""
            for i, f in enumerate(spec["files"]):
                render_tile(spec, icon_for.get((pg["id"], k)), glyph, d / f, on=i > 0, suffix=suffix)

    preview = render_preview(pages, grid, out_dir)
    return {"name": name, "model": model, "grid": grid, "pages": pages, "out": out_dir, "problems": problems,
            "warnings": warnings, "preview": preview, "uuid": (L.get("device") or {}).get("uuid", "auto")}


def render_preview(pages: list[dict], grid: dict | None, out_dir: Path) -> Path:
    from PIL import Image, ImageDraw
    cols, rows = (grid["cols"], grid["rows"]) if grid else (5, 3)
    screen = grid["screen"] if grid else []
    T, gap, pad, hdr = 140, 14, 28, 54
    pw, ph = pad * 2 + cols * T + (cols - 1) * gap, hdr + rows * T + (rows - 1) * gap + pad
    sheet = Image.new("RGB", (pw, ph * max(1, len(pages))), (11, 12, 15))
    d = ImageDraw.Draw(sheet)
    hf, wf = label_font(24), label_font(18)
    n = 0
    for i, pg in enumerate(pages):
        y0 = i * ph
        if not pg["folder"]:
            n += 1
        d.text((pad, y0 + 14), (f"Folder · {pg['title']}" if pg["folder"] else f"Page {n} · {pg['title']}"), font=hf, fill=(232, 232, 232))
        for r in range(rows):
            for c in range(cols):
                x, y, key = pad + c * (T + gap), y0 + hdr + r * (T + gap), f"{c}_{r}"
                if key in screen:
                    if key == screen[0]:
                        w = len(screen) * T + (len(screen) - 1) * gap
                        d.rounded_rectangle([x, y, x + w, y + T], radius=24, fill=(27, 30, 36))
                        d.text((x + w / 2, y + T / 2), "mini screen (clock / status)", font=wf, anchor="mm", fill=(122, 128, 140))
                    continue
                spec = pg["keys"].get(key)
                if spec:
                    with Image.open(out_dir / "pages" / pg["id"] / spec["file"]) as im:
                        sheet.paste(im.convert("RGB").resize((T, T), Image.Resampling.LANCZOS), (x, y))
                else:
                    d.rounded_rectangle([x + 4, y + 4, x + T - 4, y + T - 4], radius=24, outline=(42, 45, 52), width=2)
    out = out_dir / "preview.png"
    sheet.save(out)
    return out


def key_effect(s: dict) -> tuple[str, bool]:
    """(what pressing the key does, needs a second look). The preview only shows artwork, so the
    approval step has to show this too, especially for layouts written by someone else."""
    kind = s["kind"]
    if kind == "app":
        risky = Path(s.get("path", "")).suffix.lower() in (".bat", ".cmd", ".ps1", ".vbs", ".js", ".sh", ".command", ".py")
        return f"open {s.get('path')}", risky
    if kind == "web":
        url = str(s.get("url", ""))
        return f"open URL {url}", not url.lower().startswith(("https://", "http://"))
    if kind == "hotkey": return f"press {s.get('hotkey')}", False
    if kind == "media": return f"media {s.get('media')}", False
    if kind == "text": return f"type {s.get('text')!r}" + (" + Enter" if s.get("enter") else ""), bool(s.get("enter"))
    if kind == "folder": return f"open folder page {s.get('target')}", False
    if kind in ("back", "next", "prev"): return f"page {kind}", False
    if kind == "obs": return f"OBS {s.get('obs')}" + (f" {s['params']}" if s.get("params") else ""), False
    return f"raw {s.get('action')} {s.get('params') or {}}", True


def report(plan: dict):
    for w in plan["warnings"]:
        print(f"WARNING: {w}")
    print("KEYS (what each key does; '!' = check before approving):")
    for pg in plan["pages"]:
        print(f"  [{pg['id']}] {pg['title']}{' (folder)' if pg['folder'] else ''}")
        for k, s in sorted(pg["keys"].items(), key=lambda kv: key_order(kv[0])):
            what, risky = key_effect(s)
            print(f"   {'!' if risky else ' '} {k} {str(s.get('label', ''))[:18]:18} {what}")
    if plan["problems"]:
        print("VALIDATION PROBLEMS:")
        for p in plan["problems"]:
            print(f"  - {p}")
    else:
        print(f"VALIDATION OK ({len(plan['pages'])} pages, {sum(len(p['keys']) for p in plan['pages'])} keys)")
    print(f"PREVIEW {plan['preview']}")


def cmd_build(args):
    plan = build(Path(args.layout), Path(args.out) if args.out else None)
    report(plan)
    if plan["problems"]:
        sys.exit(2)


# ----------------------------------------------------------------------------- apply / restore
def cmd_apply(args):
    if OS not in ("Windows", "Darwin"):
        die("Ulanzi Studio only exists for Windows and macOS. On Linux see references/platforms.md.")
    plan = build(Path(args.layout), Path(args.out) if args.out else None)
    report(plan)
    if plan["problems"]:
        die("fix the validation problems before apply", 2)
    root, verified = deck_root()
    assert root
    if (not verified or not (plan["grid"] or {}).get("verified")) and not args.force_unverified:
        die("this data folder or device model is not verified for direct profile writes. Calibrate first "
            "(references/platforms.md), then re-run with --force-unverified.")
    devs, _ = device_settings(root)
    dev_uuid = plan["uuid"] if plan["uuid"] not in (None, "", "auto") else next((d["UUID"] for d in devs if d.get("Model") == plan["model"]), None)
    if not dev_uuid:
        die(f"no {plan['model']} in device_source.json. Connect it and open Ulanzi Studio once.")
    same = [p for p in profiles(root) if p["name"] == plan["name"]]
    if same and not args.replace:
        die(f"a profile named {plan['name']!r} already exists ({', '.join(p['dir'].name for p in same)}). Use --replace or rename profileName.")
    if not app_exe():
        die("Ulanzi Studio is not installed.")

    app_stop()
    backup = root.parent / f"{root.name}_backup_{_dt.datetime.now():%Y%m%d_%H%M%S}"
    try:
        shutil.copytree(root, backup)
    except BaseException:
        shutil.rmtree(backup, ignore_errors=True)
        app_start()
        die("could not back up the data folder (disk full or permissions?); nothing was changed, Ulanzi Studio restarted.")
    print(f"BACKUP {backup}")

    # Write the new profile completely into a staging folder (a name the app ignores), then swap it
    # in, and only then remove the profile it replaces. Any failure leaves the old profile intact.
    pid = str(uuid.uuid4())
    prof_dir = root / "ProfilesV2" / f"{pid}.ulanziProfile"
    staging = root / "ProfilesV2" / f".staging-{pid}"
    sp = root / "Config" / "setting_source.json"
    done = False
    try:
        write_profile(plan, staging, prof_dir, dev_uuid)
        staging.rename(prof_dir)
        print(f"PROFILE {prof_dir}")
        for p in same:
            shutil.rmtree(p["dir"])
            print(f"REMOVED old profile {p['dir'].name}")
        if not args.no_activate:
            sett = read_json(sp)
            for d in sett.get("Devices", []):
                if d.get("CurrentDevice") == dev_uuid:
                    d["CurrentProfile"] = plan["name"]
            write_json(sp, sett)
            print(f"ACTIVATED {plan['name']!r}")
        done = True
    finally:
        if not done:
            shutil.rmtree(staging, ignore_errors=True)
            print(f"ERROR while writing the profile; Ulanzi Studio is being restarted. Backup: {backup}\n"
                  f"If anything looks wrong: ulanzi.py restore --backup \"{backup}\"", file=sys.stderr)
            app_start()

    # The app re-saves a profile when it loads it (often byte-identical, so compare the modification
    # time, not the content); that rewrite is the evidence it accepted the files.
    written = (prof_dir / "manifest.json").stat().st_mtime_ns
    app_start()
    resaved = False
    for _ in range(max(1, args.wait)):
        time.sleep(1)
        m = prof_dir / "manifest.json"
        if m.exists() and m.stat().st_mtime_ns != written:
            resaved = True
            break
    cur = next((d.get("CurrentProfile") for d in read_json(sp).get("Devices", []) if d.get("CurrentDevice") == dev_uuid), None)
    running = app_running()
    ok = running and resaved and (args.no_activate or cur == plan["name"])
    status = "OK" if ok else "UNCONFIRMED"
    print(f"VERIFY running={running} app_resaved_profile={resaved} current={cur!r} -> {status}")
    if not ok:
        print("The files are in place but the app has not confirmed it loaded them. Open Ulanzi Studio and check the profile; "
              f"to roll back: ulanzi.py restore --backup \"{backup}\"")


def write_profile(plan: dict, stage: Path, final: Path, dev_uuid: str):
    """Write profile + page manifests into `stage`; image paths already point at `final`."""
    guid = {pg["id"]: pg["guid"] for pg in plan["pages"]}
    screen = (plan["grid"] or {}).get("screen", [])
    for pg in plan["pages"]:
        pdir = stage / "Profiles" / pg["guid"]
        shutil.copytree(plan["out"] / "pages" / pg["id"], pdir / "Images", ignore=shutil.ignore_patterns("src_*"))
        final_imgs = final / "Profiles" / pg["guid"] / "Images"

        def vp(f: str, text: str = "") -> dict:
            return {"Icon": str(final_imgs / f).replace("\\", "/"), "IconRel": f"Images/{f}", "Text": text}

        actions = {}
        for k, s in sorted(pg["keys"].items(), key=lambda kv: key_order(kv[0])):
            kind = s["kind"]
            # Rendered keys have the label baked in (Text stays empty so it is not drawn twice);
            # exported keys keep the title the app drew over their original image.
            text = s.get("title", "") if (s.get("image") or s.get("images")) else ""
            a = {"Action": "", "ActionID": str(uuid.uuid4()), "ActionParam": {}, "LinkedTitle": True, "Name": s.get("label", ""),
                 "Plugin": PLUGINS["system"], "State": 0, "ViewParam": [vp(f, text) for f in s["files"]]}
            if kind == "app": a.update(Action=A + "system.open", ActionParam={"Path": s["path"]})
            elif kind == "web": a.update(Action=A + "system.website", ActionParam={"Url": s["url"]})
            elif kind == "hotkey": a.update(Action=A + "system.hotkey", ActionParam={"Hotkey": s["hotkey"]})
            elif kind == "media": a.update(Action=A + "system.multimedia", ActionParam={"Hotkey": s["media"]})
            elif kind == "text": a.update(Action=A + "system.text", ActionParam={"Text": s.get("text", ""), "Enter": bool(s.get("enter"))})
            elif kind == "folder": a.update(Action=A + "page.folder", Plugin=PLUGINS["pages"], ActionParam={"ProfileUUID": guid[s["target"]]})
            elif kind in ("back", "next", "prev"): a.update(Action=A + "page." + kind, Plugin=PLUGINS["pages"])
            elif kind == "obs": a.update(Action=A + "obsstudio." + s["obs"], Plugin=PLUGINS["obs"])
            elif kind == "raw": a.update(Action=s["action"], Plugin=s.get("plugin") or {})
            if s.get("params"):
                a["ActionParam"].update(s["params"])
            actions[k] = a
        if screen:
            actions[screen[0]] = {"Action": A + "smallwindow.window", "ActionID": str(uuid.uuid4()), "ActionParam": pg.get("screen") or {"SmallViewMode": 1},
                                  "LinkedTitle": True, "Name": "Background setting", "Plugin": {}, "State": 0, "ViewParam": [{"Icon": ""}]}
        write_json(pdir / "manifest.json", {"Controllers": [{"Actions": {}, "Type": "Encoder"}, {"Actions": actions, "Type": "Keypad"}],
                                            "Icon": "", "Name": pg["title"]})
    top = [pg for pg in plan["pages"] if not pg["folder"]]
    from PIL import Image
    first = next((s for pg in top for s in pg["keys"].values()), None)
    if first:
        src = plan["out"] / "pages" / next(pg["id"] for pg in top if first in pg["keys"].values()) / first["file"]
        with Image.open(src) as im:
            im.resize((48, 48), Image.Resampling.LANCZOS).save(stage / "icon_profile.png")
    write_json(stage / "manifest.json", {"Device": {"Model": plan["model"], "UUID": dev_uuid}, "Icon": "icon_profile.png" if first else "",
                                         "Name": plan["name"], "Pages": {"Current": top[0]["guid"], "Pages": [pg["guid"] for pg in top]},
                                         "Version": 2})


def cmd_restore(args):
    root, _ = deck_root()
    assert root
    b = Path(args.backup).resolve()
    live = root.resolve()
    if b == live or live in b.parents:
        die(f"{b} is the live data folder (or inside it); pass a UlanziDeck_backup_* folder")
    if not ((b / "ProfilesV2").is_dir() and (b / "Config" / "device_source.json").is_file()):
        die(f"{b} is not an Ulanzi data backup (needs ProfilesV2/ and Config/device_source.json)")
    ts = f"{_dt.datetime.now():%Y%m%d_%H%M%S}"
    staging = root.parent / f"{root.name}_restoring_{ts}"
    aside = root.parent / f"{root.name}_pre_restore_{ts}"
    app_stop()
    moved = False
    try:
        shutil.copytree(b, staging)          # copy first: a failure here leaves the live folder untouched
        shutil.move(str(root), str(aside))
        moved = True
        staging.rename(root)
        print(f"RESTORED {b.name} (previous state kept at {aside})")
    except BaseException:
        if moved and not root.exists():
            shutil.move(str(aside), str(root))   # put the original back
        shutil.rmtree(staging, ignore_errors=True)
        print("ERROR: restore failed; the data folder was left as it was.", file=sys.stderr)
        raise
    finally:
        app_start()


# ----------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("state").set_defaults(fn=cmd_state)
    p = sp.add_parser("keymap"); p.add_argument("--profile", default="current"); p.set_defaults(fn=cmd_keymap)
    p = sp.add_parser("find-apps"); p.add_argument("--filter"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_find_apps)
    p = sp.add_parser("export"); p.add_argument("--profile", default="current"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--name", help="profileName to write in the layout (default: same name; use a new name to copy a stock profile)")
    p.add_argument("--keep-paths", action="store_true", help="keep raw launch paths instead of portable app names")
    p.set_defaults(fn=cmd_export)
    p = sp.add_parser("build"); p.add_argument("--layout", required=True); p.add_argument("--out"); p.set_defaults(fn=cmd_build)
    p = sp.add_parser("apply"); p.add_argument("--layout", required=True); p.add_argument("--out")
    p.add_argument("--replace", action="store_true", help="replace an existing profile with the same name")
    p.add_argument("--no-activate", action="store_true"); p.add_argument("--force-unverified", action="store_true")
    p.add_argument("--wait", type=int, default=20, help="seconds to wait for the app to re-save the profile"); p.set_defaults(fn=cmd_apply)
    p = sp.add_parser("restore"); p.add_argument("--backup", required=True); p.set_defaults(fn=cmd_restore)
    args = ap.parse_args()
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8", errors="replace")
    args.fn(args)


if __name__ == "__main__":
    main()

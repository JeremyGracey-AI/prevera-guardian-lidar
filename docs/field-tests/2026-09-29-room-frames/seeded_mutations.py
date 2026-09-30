#!/usr/bin/env python3
"""Seeded mutations of the room-frame runner and scorer: each one must make at least one test fail.

Record for docs/field-tests/2026-09-29-room-frames-results.md, section 6. Each mutant is one textual edit of
jetson/rf_room_eval.py or tools/bag_analysis/score_room_frames.py that breaks a rule the plan declares; the test
suite (src/prevera_perception/test/test_room_frames.py) is run against it and must fail. Files are restored after
every mutant. The output committed beside this script (seeded-mutations.txt) is the run of 2026-09-29.

Usage, from the repository root:
    python3 docs/field-tests/2026-09-29-room-frames/seeded_mutations.py [python-with-pytest]
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
S = ROOT / "tools/bag_analysis/score_room_frames.py"
R = ROOT / "jetson/rf_room_eval.py"
PY = sys.argv[1] if len(sys.argv) > 1 else sys.executable

MUTANTS = [
    ("M1 same-class top reads tie", S, 'return classes.pop() if len(classes) == 1 else "tie"', 'return classes.pop() if len([p for p in poses if p["confidence"] == top]) == 1 else "tie"'),
    ("M2 class match case-insensitive", S, 'well_formed(p) and p["class"] in POSES and p["confidence"] >= conf]', 'well_formed(p) and p["class"].lower() in POSES and p["confidence"] >= conf]'),
    ("M3 errors do not invalidate", S, '    if errors:\n        out.append', '    if False:\n        out.append'),
    ("M4 bed counted under threshold", S, 'p["class"] == "bed" and p["confidence"] >= conf)', 'p["class"] == "bed")'),
    ("M5 error row read from predictions", S, 'r = "error" if f.get("error") else reading', 'r = reading'),
    ("M6 R2 failing list omits ties", S, 'and r in ("lying", "tie")]', 'and r in ("lying",)]'),
    ("M6b R2 ignores ties in the bar", S, 'at_most_5(w["lying"] + w["tie"], w["n"])', 'at_most_5(w["lying"], w["n"])'),
    ("M7 row count unchecked", S, '    if len(frames) != FRAMES:', '    if False:'),
    ("M7b group counts unchecked", S, '            if counts.get((seg, cam), 0) != n:', '            if False:'),
    ("M7c duplicates unchecked", S, '        if f.get("file") in seen:', '        if False:'),
    ("M7d unexpected groups unchecked", S, '        if seg not in EXPECTED or cam not in CAMERAS:', '        if False:'),
    ("M7e unknown classes unchecked", S, '    if other:\n', '    if False:\n'),
    ("M7f summary values unchecked", S, '           if type(summary.get(k, missing)) is not type(v) or summary.get(k, missing) != v]', '           if False]'),
    ("M7g names and order unchecked", S, '    if names_digest(frames) != FILES_SHA256:', '    if False:'),
    ("M7h rows digest unchecked", S, '    if summary.get("rows_sha256") != rows_digest(frames):', '    if False:'),
    ("M7i loose equality", S, 'if type(summary.get(k, missing)) is not type(v) or summary.get(k, missing) != v]', 'if summary.get(k, missing) != v]'),
    ("M7j server version unchecked", S, '"url": URL, "server_version": SERVER, "complete": True,', '"url": URL, "complete": True,'),
    ("M16 printed R1 is per-segment", S, "{'PASS' if r1['pass'] else 'FAIL'}\"\n                 f\" · carried by", "{'PASS' if r1['per_segment_reading'] else 'FAIL'}\"\n                 f\" · carried by"),
    ("M17 invalid run still exits 0", S, 'sys.exit(0 if s["valid"] else 2)', 'sys.exit(0)'),
    ("M18 R1 per-segment as verdict", S, '"pass": bool(carried_by)', '"pass": all(any(clears(seg, cam) for cam in CAMERAS) for seg in ("B", "F"))'),
    ("M19 80% bar loosened", S, 'return n > 0 and 5 * hits >= 4 * n', 'return n > 0 and 5 * hits >= 4 * n - 5'),
    ("M20 5% bar loosened", S, 'return n > 0 and 20 * hits <= n', 'return n > 0 and 20 * hits <= n + 10'),
    ("N12 invalid run prints the table", S, '    if not s["valid"]:\n        lines.append("INVALID RUN: no verdict on R1 or R2, and no reading is shown.")', '    if not s["valid"]:\n        lines += [f"{k} {c}" for k, c in s["cells"].items()]\n        lines.append("INVALID RUN: no verdict on R1 or R2, and no reading is shown.")'),
    ("N12b invalid score() keeps readings", S, '        out["cells"] = {k: {"n": c["n"], "error": c["error"]} for k, c in cells.items()}\n', ''),
    ("N16 unreadable file crashes", S, '    except (OSError, ValueError, KeyError, TypeError) as e:', '    except ZeroDivisionError as e:'),
    ("M8 runner rounds confidence", R, '"predictions": [{k: p.get(k) for k in KEPT} for p in out["predictions"]]})', '"predictions": [{k: (round(p.get(k), 2) if k == "confidence" else p.get(k)) for k in KEPT} for p in out["predictions"]]})'),
    ("M9 default URL not loopback", R, 'URL = "http://127.0.0.1:9001"', 'URL = "http://0.0.0.0:9001"'),
    ("M10 default confidence 0.75", R, 'CONFIDENCE = 0.56', 'CONFIDENCE = 0.75'),
    ("M11 only HTTP errors caught", R, '            except Exception as e:', '            except ZeroDivisionError as e:'),
    ("M12 predictions re-sorted", R, 'for p in out["predictions"]]})', 'for p in sorted(out["predictions"], key=lambda p: -p["confidence"])]})'),
    ("M15 extra field in body", R, '        "disable_active_learning": True,', '        "disable_active_learning": True,\n        "disable_model_monitoring": False,'),
    ("M21 AL flag dropped", R, '        "disable_active_learning": True,\n', ''),
    ("M22 overwrite allowed", R, '        out_file = open(out_path, "x")', '        out_file = open(out_path, "w")'),
    ("M23 200 without predictions accepted", R, '                if not isinstance(out, dict) or not isinstance(out.get("predictions"), list):\n                    raise ValueError("no predictions in the response")\n', ''),
    ("M25 key written to summary", R, '            "model": a.model_id,', '            "model": a.model_id, "k": key,'),
    ("N3 complete always true", R, '"complete": len(rows) == len(manifest),', '"complete": True,'),
    ("N7b SIGTERM/SIGHUP not handled", R, '    for signum in (signal.SIGTERM, signal.SIGHUP):\n        signal.signal(signum, stop)\n', ''),
    ("N7c interrupted run writes nothing", R, '        with out_file:\n            json.dump({"summary": summary, "frames": rows}, out_file, indent=1)', '        if summary["complete"]:\n            json.dump({"summary": summary, "frames": rows}, out_file, indent=1)'),
    ("N11 proxies honoured", R, 'DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))', 'DIRECT = urllib.request.build_opener()'),
    ("N14 error text uncapped", R, 'f"{type(e).__name__}: {e}"[:120]})', 'f"{type(e).__name__}: {e}"[:2000]})'),
    ("N15 Ctrl-C becomes an error row", R, '            except Exception as e:', '            except BaseException as e:'),
    ("N17 output created after the run", R, '        out_file = open(out_path, "x")', '        out_file = None if os.path.exists(out_path) and (_ for _ in ()).throw(FileExistsError()) else __import__("io").StringIO()'),
    ("N18 rows digest not recorded", R, '            "rows_sha256": rows_digest(rows),\n', ''),
    ("N19 frame digest of names", R, '                digest.update(image)', '                digest.update(m["file"].encode())'),
]


def run():
    p = subprocess.run([PY, "-m", "pytest", "test/test_room_frames.py", "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
                       cwd=ROOT / "src/prevera_perception", env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin"},
                       capture_output=True, text=True)
    out = [line for line in p.stdout.strip().splitlines() if line.strip()]
    failed = [line for line in out if line.startswith("FAILED")][:1]
    return p.returncode, out[-1] if out else "", failed


def main():
    rc, last, _ = run()
    print("baseline:", last)
    if rc != 0:
        sys.exit("the suite must pass before mutants are seeded")
    survivors = []
    for name, path, old, new in MUTANTS:
        src = path.read_text()
        if src.count(old) != 1:
            print(f"NOT APPLIED {name}: pattern found {src.count(old)} times")
            survivors.append(name + " (not applied)")
            continue
        try:
            path.write_text(src.replace(old, new))
            rc, last, failed = run()
        finally:
            path.write_text(src)
        print("caught  " if rc != 0 else "SURVIVES", name, "|", failed[0][7:110] if failed else last)
        if rc == 0:
            survivors.append(name)
    print(f"\n{len(MUTANTS)} mutants, {len(MUTANTS) - len(survivors)} caught, survivors: {survivors}")
    print("restored baseline:", run()[1])
    sys.exit(1 if survivors else 0)


if __name__ == "__main__":
    main()

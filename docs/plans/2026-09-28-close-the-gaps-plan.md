# Close the Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every item the 2026-09-28 branch left open that can be closed with the hardware and people available
on 2026-09-28: the four deferred review minors, the two privacy and co-load gaps carried since 2026-09-27, the
bridge exposure ruling, the unversioned runner, and the release tag.

**Architecture:** Repository fixes first (CI, URDF, tests), each with a failing test first, on a branch off `main`
after PR #2 merges. Then the two measurements on the Jetson, with their bars fixed in this document before they run
(DR-17). Then the documents that carry the gaps are updated to say "closed, here is the evidence", and the branch
goes through a PR and CI like the others. Nothing here touches the detector's behaviour; the only device-side
behaviour change (bridge binding, Task 7) is opt-in through a decision recorded in Global Constraints.

**Tech Stack:** Python 3.10, pytest, xacro (pip), PyYAML, `mcap` + `mcap-ros2-support` (already harness
requirements), ROS 2 Humble on the Jetson (`ros2 bag`), Roboflow Inference 1.7.2 container, `tcpdump` (Jeremy,
`sudo`), GitHub Actions.

**Spec:** the open items as recorded in `docs/field-tests/HANDOFF-2026-09-28.md` ("Review pass", deferred minors),
`docs/field-tests/2026-09-27-rfdetr-results.md` section 7 (privacy, code and co-load), DR-11's "Consequences and
gaps", and `docs/field-tests/2026-09-28-roboflow-finetune-results.md` section 7 (F5 co-load and egress).

## Global Constraints

- No frame from the test room leaves the device (DR-11). Every request in Tasks 5 and 6 goes to `127.0.0.1:9001`.
- Pre-declared evaluations (DR-17): this plan is committed before Task 5 or Task 6 runs; the bars in those tasks do
  not move afterwards; a failed bar is reported as a finding beside an unchanged verdict.
- The push gate (DR-17) stands: every `git push` in this plan is run with `ALLOW_PUSH=1` only on Jeremy's
  instruction for that push; every `sudo` line on the Jetson is Jeremy's.
- Commit trailers on every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01K1wULiXGokmRbxVsVLQ9Ho`.
- Test command, from `src/prevera_perception`: `PYTHONPATH=. ../../.venv310/bin/python -m pytest test/ -q`
  (99 passed, 1 skipped at `9fa6971`). CI runs the same on Python 3.10, numpy 1.x.
- Decisions this plan needs from Jeremy before the task that uses them (recorded here once made):
  - D-a: bridges default to loopback (Task 7) — **yes** (Jeremy, 2026-09-28 23:2x UTC).
  - D-b: `rf_eval.py` enters the repo (Task 8) — **yes** (same).
  - D-c: merge PR #2 with a merge commit before branching (Task 0) — **yes, agent runs the merge** (same); merged as `03c9fa4`.
- Branch: `gaps-2026-09-28`, off `main` after PR #2 merges. Never rewrite history on it (the plan commit's
  timestamp is evidence for Tasks 5 and 6).

## Review Focus

1. A xacro expansion with `lidar_mount_height` below the housing's own height (e.g. `0.01`) must not draw a negative
   or zero-length mast — Task 2's test covers `0.02` and `0.65`; add the `0.01` case there.
2. The workflow-spec test must fail, not skip, when `fall_detector.yaml` moves or the key is renamed — Task 3
   asserts the key is present rather than defaulting to 4.0.
3. `scan_rate()` must not divide by zero on a bag with one `/scan` message or none — Task 5's test covers an
   empty list and a singleton.
4. The egress summary must classify a destination it cannot resolve as "unknown, counted against the bar", never
   silently drop it — Task 6's parser counts every non-LAN packet before any name lookup.
5. `guardian-up.sh` with `GUARDIAN_BIND` empty must bind loopback, as `mjpeg_server.py` already does (review
   finding M5) — Task 7's test passes an empty value.

---

### Task 0: Merge PR #2 and branch (Jeremy's go, D-c)

**Files:** none in the repo.

- [ ] **Step 1: Merge PR #2 with a merge commit** (chronology is evidence). Jeremy, in a terminal on the Mac:

```bash
cd ~/src/github.com/JeremyGracey-AI/prevera-guardian-lidar
gh pr merge 2 --merge --subject "Merge pull request #2 from JeremyGracey-AI/roboflow-finetune-2026-09-28"
git checkout main && git pull
```

- [ ] **Step 2: Branch**

```bash
git checkout -b gaps-2026-09-28
```

- [ ] **Step 3: Commit this plan first**

```bash
git add docs/plans/2026-09-28-close-the-gaps-plan.md
git commit -m "docs(plans): close-the-gaps plan, bars for the co-load and egress measurements fixed before they run"
```

---

### Task 1: CI hygiene (review M8)

**Files:**
- Modify: `.github/workflows/tests.yml`
- Test: `src/prevera_perception/test/test_ci_workflow.py` (create)

**Interfaces:** none.

- [ ] **Step 1: Write the failing test**

```python
"""The CI workflow keeps the properties the 2026-09-28 review asked for (M8)."""
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "tests.yml"


def _load():
    # PyYAML reads the bare `on:` key as boolean True; normalise it.
    d = yaml.safe_load(WF.read_text())
    return {("on" if k is True else k): v for k, v in d.items()}


def test_runs_once_per_change_not_twice():
    on = _load()["on"]
    assert on["push"] == {"branches": ["main"]}, "push runs only on main; branches get their run from pull_request"
    assert "pull_request" in on


def test_token_is_read_only():
    assert _load()["permissions"] == {"contents": "read"}


def test_shell_check_uses_sh_for_the_sh_hook():
    run = _load()["jobs"]["pytest"]["steps"][-1]["run"]
    assert "sh -n tools/git-hooks/pre-push" in run
    assert "tools/git-hooks/pre-push" not in run.split("sh -n")[0], "the #!/bin/sh hook is not parsed by bash"
```

- [ ] **Step 2: Run it, expect three failures**

Run: `PYTHONPATH=. ../../.venv310/bin/python -m pytest test/test_ci_workflow.py -q`
Expected: 3 failed (`push` is `None`, no `permissions`, `bash -n` loop covers the hook).

- [ ] **Step 3: Edit the workflow**

Replace the `on:` block and add `permissions:` right after it; replace the last step:

```yaml
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
```

```yaml
      - name: Shell scripts parse
        run: |
          for f in jetson/*.sh setup_jetson.sh; do bash -n "$f"; done
          sh -n tools/git-hooks/pre-push
```

- [ ] **Step 4: Run the test file, then the suite**

Expected: 3 passed; suite 102 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tests.yml src/prevera_perception/test/test_ci_workflow.py
git commit -m "ci: read-only token, one run per change, sh -n for the sh hook (review M8)"
```

---

### Task 2: URDF mast and launch argument (review M7), laser-height assertion (M8)

**Files:**
- Modify: `src/prevera_description/urdf/sentinel.urdf.xacro` (after the `lidar_mount` link)
- Modify: `src/prevera_description/launch/state_publisher.launch.py`
- Test: `src/prevera_perception/test/test_urdf_geometry.py` (create)
- Modify: `tools/bag_analysis/requirements.txt` (add `xacro`, so the test runs in CI and in `.venv310`)

**Interfaces:** the xacro arg `lidar_mount_height` (metres, default `0.02`); the launch argument of the same name.

- [ ] **Step 1: Write the failing tests**

```python
"""sentinel.urdf.xacro puts the laser at lidar_mount_height and draws a mast only when there is room for one."""
import xml.dom.minidom
from pathlib import Path

import pytest

xacro = pytest.importorskip("xacro")
ROOT = Path(__file__).resolve().parents[3]
URDF = ROOT / "src" / "prevera_description" / "urdf" / "sentinel.urdf.xacro"
LAUNCH = ROOT / "src" / "prevera_description" / "launch" / "state_publisher.launch.py"


def _expand(height=None):
    mappings = {"lidar_mount_height": str(height)} if height is not None else {}
    doc = xacro.process_file(str(URDF), mappings=mappings)
    return xml.dom.minidom.parseString(doc.toxml())


def _joints(dom):
    out = {}
    for j in dom.getElementsByTagName("joint"):
        parent = j.getElementsByTagName("parent")[0].getAttribute("link")
        child = j.getElementsByTagName("child")[0].getAttribute("link")
        z = float(j.getElementsByTagName("origin")[0].getAttribute("xyz").split()[2])
        out[child] = (parent, z)
    return out


def _laser_height(dom):
    joints, link, z = _joints(dom), "laser", 0.0
    while link != "base_link":
        link, dz = joints[link]
        z += dz
    return z


@pytest.mark.parametrize("height", [None, 0.02, 0.65, 0.01])
def test_laser_sits_at_lidar_mount_height(height):
    assert abs(_laser_height(_expand(height)) - (0.02 if height is None else height)) < 1e-9


def test_mast_only_when_the_housing_would_float():
    links = lambda dom: {l.getAttribute("name") for l in dom.getElementsByTagName("link")}
    assert "lidar_mast" not in links(_expand(0.02))
    assert "lidar_mast" not in links(_expand(0.01))
    dom = _expand(0.65)
    assert "lidar_mast" in links(dom)
    mast = [l for l in dom.getElementsByTagName("link") if l.getAttribute("name") == "lidar_mast"][0]
    length = float(mast.getElementsByTagName("cylinder")[0].getAttribute("length"))
    assert abs(length - (0.65 - 0.041 / 2 - 0.005)) < 1e-9, "mast from the top of the base plate to the housing"


def test_launch_file_exposes_the_argument():
    text = LAUNCH.read_text()
    assert '"lidar_mount_height"' in text and "lidar_mount_height:=" in text
```

- [ ] **Step 2: Install xacro into the venv and run, expect failures**

Run: `../../.venv310/bin/pip install xacro` then the test file.
Expected: `test_mast_only_when_the_housing_would_float` FAIL (no `lidar_mast`), `test_launch_file_exposes_the_argument`
FAIL; the height tests pass already (they pin existing behaviour and the `0.01` edge).

- [ ] **Step 3: URDF** — add after the `lidar_mount` link, before `<link name="laser"/>`:

```xml
  <!-- Mast between the base plate (0.005 m thick) and the housing, drawn only when the scan window sits high
       enough for one: the original 0.65 m rig had a 0.55 m mast on a 0.10 m base; the floor mount has none. Visual only. -->
  <xacro:property name="mast_length" value="${lidar_mount_height - lidar_height / 2 - 0.005}"/>
  <xacro:if value="${mast_length > 0.001}">
    <link name="lidar_mast">
      <visual>
        <origin xyz="0 0 ${mast_length / 2}" rpy="0 0 0"/>
        <geometry>
          <cylinder length="${mast_length}" radius="0.012"/>
        </geometry>
        <material name="prevera_steel"/>
      </visual>
    </link>
    <joint name="base_to_mast" type="fixed">
      <parent link="base_link"/>
      <child  link="lidar_mast"/>
      <origin xyz="0 0 0.005" rpy="0 0 0"/>
    </joint>
  </xacro:if>
```

Move the `prevera_steel` material definition (name + color) into the `lidar_mount` visual as it is; URDF resolves a
later `<material name="prevera_steel"/>` reference to the first definition in the file.

- [ ] **Step 4: Launch file** — declare and pass the argument:

```python
        DeclareLaunchArgument(
            "lidar_mount_height",
            default_value="0.02",
            description="Scan window height above the floor, metres; 0.65 draws the original mast rig",
        ),
```

```python
                "robot_description": Command([
                    "xacro ", str(xacro), " lidar_mount_height:=", LaunchConfiguration("lidar_mount_height"),
                ]),
```

- [ ] **Step 5: Add `xacro` to `tools/bag_analysis/requirements.txt`** (one line) and run the test file, then the suite.

Expected: 6 passed in the file; suite green.

- [ ] **Step 6: Commit**

```bash
git add src/prevera_description tools/bag_analysis/requirements.txt src/prevera_perception/test/test_urdf_geometry.py
git commit -m "description: mast under the raised rig, lidar_mount_height exposed in the launch file; laser-height test (review M7, M8)"
```

---

### Task 3: Workflow-spec test reads `sustained_down_s` from the config (review M10)

**Files:**
- Modify: `src/prevera_perception/test/test_roboflow_workflow_spec.py:51-54`

- [ ] **Step 1: Replace the hard-coded test**

```python
CONFIG = Path(__file__).resolve().parents[3] / "src" / "prevera_bringup" / "config" / "fall_detector.yaml"


def _sustained_down_s():
    import yaml
    params = yaml.safe_load(CONFIG.read_text())
    node = next(iter(params.values()))["ros__parameters"]
    assert "sustained_down_s" in node.get("fall", node), "fall_detector.yaml no longer names sustained_down_s"
    return float(node.get("fall", node)["sustained_down_s"])


def test_warn_threshold_matches_the_lidar_sustained_rule():
    spec = json.loads(SPEC.read_text())
    warn = {i["name"]: i for i in spec["inputs"]}["warn_after_s"]["default_value"]
    assert warn == _sustained_down_s(), "keep warn_after_s equal to fall_detector.yaml's sustained_down_s or update the README"
```

- [ ] **Step 2: Verify it reads the real key.** Run the file: PASS. Then temporarily change the yaml's value to 5.0,
run again: FAIL with the message; restore the yaml (`git checkout src/prevera_bringup/config/fall_detector.yaml`).

- [ ] **Step 3: Commit**

```bash
git add src/prevera_perception/test/test_roboflow_workflow_spec.py
git commit -m "test(roboflow): warn_after_s is checked against fall_detector.yaml, not a literal (review M10)"
```

---

### Task 4: `scan_rate` tool for the co-load bags

**Files:**
- Create: `tools/bag_analysis/scan_rate.py`
- Test: `src/prevera_perception/test/test_scan_rate.py` (create)

**Interfaces:**
- Produces: `scan_rate(stamps_s: list[float]) -> dict` with keys `count`, `duration_s`, `hz`, `max_gap_s`,
  `gaps_over_0_5_s`; and a CLI `python3 tools/bag_analysis/scan_rate.py <bag-dir> [--topic /scan] [--events /fall_events]`
  printing one JSON object per bag with those keys plus `events` (message count on the events topic).

- [ ] **Step 1: Write the failing tests**

```python
"""scan_rate() summarises /scan arrival from header stamps: count, rate, the largest gap, gaps over half a second."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "bag_analysis"))
from scan_rate import scan_rate  # noqa: E402


def test_steady_ten_hertz():
    r = scan_rate([i * 0.1 for i in range(600)])
    assert r["count"] == 600 and abs(r["hz"] - 10.0) < 1e-6 and abs(r["max_gap_s"] - 0.1) < 1e-9
    assert r["gaps_over_0_5_s"] == 0


def test_one_dropout_is_counted_once():
    stamps = [i * 0.1 for i in range(100)] + [i * 0.1 + 0.8 for i in range(100, 200)]
    r = scan_rate(stamps)
    assert r["gaps_over_0_5_s"] == 1 and abs(r["max_gap_s"] - 0.9) < 1e-9


def test_empty_and_singleton_do_not_divide_by_zero():
    assert scan_rate([]) == {"count": 0, "duration_s": 0.0, "hz": None, "max_gap_s": None, "gaps_over_0_5_s": 0}
    assert scan_rate([3.0])["count"] == 1 and scan_rate([3.0])["hz"] is None
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""Arrival statistics of /scan (and a count of /fall_events) in a rosbag2 mcap directory, from header stamps.

Written for the co-load measurement of docs/plans/2026-09-28-close-the-gaps-plan.md, Task 5: the same bar
applied to an idle bag and a bag recorded while the Inference container was serving frames.

Usage: scan_rate.py <bag-dir> [<bag-dir> ...] [--topic /scan] [--events /fall_events]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def scan_rate(stamps_s):
    stamps = sorted(stamps_s)
    if len(stamps) < 2:
        return {"count": len(stamps), "duration_s": 0.0, "hz": None, "max_gap_s": None, "gaps_over_0_5_s": 0}
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    duration = stamps[-1] - stamps[0]
    return {"count": len(stamps), "duration_s": round(duration, 3), "hz": (len(stamps) - 1) / duration,
            "max_gap_s": max(gaps), "gaps_over_0_5_s": sum(1 for g in gaps if g > 0.5)}


def summarise(bag, topic, events):
    from replay_detector import _iter_mcap  # header stamps from the mcap files in the bag directory
    stamps, n_events = [], 0
    for name, log_ns, pub_ns, msg in _iter_mcap(bag):
        if name == topic:
            stamps.append(msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9)
        elif name == events:
            n_events += 1
    return {"bag": str(bag), **scan_rate(stamps), "events": n_events}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bags", nargs="+")
    ap.add_argument("--topic", default="/scan")
    ap.add_argument("--events", default="/fall_events")
    a = ap.parse_args()
    for bag in a.bags:
        print(json.dumps(summarise(bag, a.topic, a.events)))


if __name__ == "__main__":
    main()
```

Check `_iter_mcap`'s tuple order in `replay_detector.py` before relying on it (`(topic, log_ns, pub_ns, msg)` at
`replay_detector.py:280`); adjust the unpacking if it differs.

- [ ] **Step 4: Run the tests, then the suite**

- [ ] **Step 5: Commit**

```bash
git add tools/bag_analysis/scan_rate.py src/prevera_perception/test/test_scan_rate.py
git commit -m "tools(bag_analysis): scan_rate, arrival statistics for the co-load measurement"
```

---

### Task 5: Co-load measurement on the Jetson (pre-declared; bars fixed here)

**Files:**
- Create: `docs/field-tests/2026-09-28-roboflow/coload-idle.json`, `coload-e65db0.json` (the `scan_rate` output)
- Modify: `docs/field-tests/2026-09-28-roboflow-finetune-results.md` section 5 (a "Co-load" paragraph) and
  section 7 (remove the co-load line); `docs/DECISIONS.md` DR-11 "Consequences and gaps" (last sentence).

**Question:** does serving the fine-tuned model disturb the LIDAR stack while it runs?

**Procedure** (agent over ssh, no sudo; LIDAR stack up, cameras off, container up with `e65db0` resident):
1. Idle bag, 60 s: `ros2 bag record -o /opt/nvme/bags/coload-idle /scan /fall_events` (timeout 60).
2. Load bag, 60 s: start `ros2 bag record -o /opt/nvme/bags/coload-e65db0 /scan /fall_events`; after 5 s start
   `f5_device_fit.py ...--e65db0 --confidence 0.56` (580 frames, about 49 s); stop the bag at 60 s.
3. `scan_rate.py` on both bags (bags copied to the Mac; they are not committed).

**Bars, fixed now:**
- **CL1 (rate):** `count` in the load bag is within **±10 %** of `count` in the idle bag. PASS / FAIL.
- **CL2 (dropouts):** `gaps_over_0_5_s` is **0** in the load bag, given it is 0 in the idle bag; if the idle bag
  itself has a gap over 0.5 s the bar is "not testable today" and both figures are reported.
- **Report only:** `/fall_events` counts (nobody is asked to be in the room; a non-zero count is reported, not
  judged), and the runner's latency median during the recording beside the 78.7 ms of the earlier run.

- [ ] **Step 1: Confirm preconditions** (`~/guardian-status.sh`: driver 1, detector 1, about 50 scans; no camera
  process; `/info` on 9001).
- [ ] **Step 2: Record the idle bag.**
- [ ] **Step 3: Record the load bag with the runner inside it.**
- [ ] **Step 4: Copy both bags to the Mac (`~/src/.../prevera-guardian-lidar/.bags/`, gitignored) and run
  `scan_rate.py`** on each; save the two JSON lines under `docs/field-tests/2026-09-28-roboflow/`.
- [ ] **Step 5: Write the verdicts into results section 5**, in a "Co-load" paragraph, with the bars quoted as above
  and the figures; delete the "co-load during a run" clause from section 7; update DR-11's last sentence
  ("Whether inference disturbs `/scan` under load is not yet measured" → measured, with the verdict and a link).
- [ ] **Step 6: Commit** `git commit -m "field-tests: co-load measured, CL1/CL2 verdicts (plan bars unchanged)"`.

---

### Task 6: Egress capture (pre-declared; Jeremy's `sudo`, agent drives the runner)

**Files:**
- Create: `tools/jetson/egress_summary.py` (parses `tcpdump -r … -n -q -tt` text)
- Test: `src/prevera_perception/test/test_egress_summary.py`
- Create: `docs/field-tests/2026-09-28-roboflow/egress-e65db0.json` (the summary; the pcap stays on the Jetson)
- Modify: results section 5 and 7; DR-11 status line ("privacy verification incomplete" → what is now verified).

**Question:** during a full run against the local container, what leaves the Jetson, to where, how much?

**Bars, fixed now:**
- **EG1 (frames stay):** bytes sent from the Jetson to any address outside the LAN (`192.168.4.0/24`, link-local,
  multicast) during the 580-frame loop total **under 200 KB**. One frame is about 100 KB; 580 frames are about
  60 MB; the bar is two orders of magnitude below that. PASS / FAIL.
- **EG2 (destinations):** every non-LAN destination that received bytes resolves to a Roboflow host
  (`*.roboflow.com`, or the storage host Roboflow's `getWeights` answer names) or an NTP/DNS server. Any other
  destination is a FAIL with the address listed.
- **Report only:** bytes per destination, packets during warm-up versus during the loop, and whether the model
  had to be pulled (it should not: `e65db0` is cached).

**Procedure:**
0. Agent: `LANIF=$(ip -o route get 1.1.1.1 | awk '{print $5}')` on the Jetson (the interface that carries
   `192.168.4.39`), so the capture sees each outbound packet once, on its way out, not again on `docker0`.
1. Jeremy, in a terminal (the capture file is made readable to `jeremy` with `-Z`; replace `<lanif>`):

```bash
ssh -t jeremy@192.168.4.39 'sudo tcpdump -i <lanif> -n -Z jeremy -w /opt/nvme/reports/egress-e65db0.pcap "not port 22"'
```
   Leave it running; press Ctrl-C when the agent says the run has finished.
2. Agent: waits 10 s, runs `f5_device_fit.py ...--e65db0 --confidence 0.56`. The loop window is
   `[started_utc, started_utc + run_s]` from the runner's JSON; the whole-run window is bracketed by `date +%s`
   before and after.
3. Agent: `tcpdump -r /opt/nvme/reports/egress-e65db0.pcap -n -q -tt > /opt/nvme/reports/egress-e65db0.txt`
   on the Jetson (reading a file needs no root), then `egress_summary.py` on the text for both windows, then
   `getent hosts` for every non-LAN address it lists.

- [ ] **Step 1: Write the failing test for the parser**

```python
"""egress_summary() sums bytes by destination outside the LAN from `tcpdump -n -q -tt` lines within a time window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "jetson"))
from egress_summary import egress_summary  # noqa: E402

LINES = """1790640000.100000 IP 192.168.4.39.40000 > 34.120.1.2.443: tcp 1200
1790640000.200000 IP 192.168.4.39.40001 > 192.168.4.60.9090: tcp 500
1790640000.300000 IP 34.120.1.2.443 > 192.168.4.39.40000: tcp 300
1790640001.000000 eth0  Out IP 192.168.4.39.40002 > 8.8.8.8.53: UDP, length 40
1790640050.000000 IP 192.168.4.39.40003 > 1.2.3.4.443: tcp 100
""".splitlines()
ARGS = dict(t0=1790640000.0, t1=1790640010.0, lan="192.168.4.", self_ip="192.168.4.39")


def test_sums_outbound_bytes_to_non_lan_destinations_inside_the_window():
    s = egress_summary(LINES, **ARGS)
    assert s["out_bytes_non_lan"] == 1240
    assert s["by_destination"] == {"34.120.1.2:443": 1200, "8.8.8.8:53": 40}
    assert s["in_bytes_non_lan"] == 300


def test_lines_outside_the_window_and_lan_traffic_are_excluded():
    s = egress_summary(LINES, **ARGS)
    assert "1.2.3.4:443" not in s["by_destination"] and "192.168.4.60:9090" not in s["by_destination"]


def test_unparseable_line_is_counted_not_dropped():
    s = egress_summary(["garbage"], t0=0, t1=1e12, lan="192.168.4.", self_ip="192.168.4.39")
    assert s["unparsed_lines"] == 1
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement `tools/jetson/egress_summary.py`**

```python
#!/usr/bin/env python3
"""Sum bytes by destination outside the LAN in `tcpdump -n -q -tt` output, inside a time window.

Usage: egress_summary.py <tcpdump-text> --t0 <epoch> --t1 <epoch> [--lan 192.168.4.] [--self-ip 192.168.4.39]
Every line that does not parse is counted in `unparsed_lines`, never dropped silently.
"""
import argparse
import json
import re

LINE = re.compile(r"^(?P<t>\d+\.\d+)\s+(?:\S+\s+(?:In|Out)\s+)?IP6?\s+(?P<src>[\w.:]+?)\.(?P<sp>\d+)\s+>\s+"
                  r"(?P<dst>[\w.:]+?)\.(?P<dp>\d+):\s+(?:tcp\s+(?P<tcp>\d+)|UDP, length (?P<udp>\d+)|(?P<other>.*))$")


def _is_lan(addr, lan):
    return addr.startswith(lan) or addr.startswith("127.") or addr.startswith("169.254.") or addr.startswith("224.") \
        or addr.startswith("239.") or addr.startswith("fe80") or addr.startswith("ff")


def egress_summary(lines, t0, t1, lan, self_ip):
    """Direction comes from the Jetson's own address (src == self_ip is outbound), so the interface and In/Out
    columns tcpdump prints only for `-i any` are optional."""
    out = {"out_bytes_non_lan": 0, "in_bytes_non_lan": 0, "by_destination": {}, "unparsed_lines": 0, "lines": 0}
    for line in lines:
        if not line.strip():
            continue
        out["lines"] += 1
        m = LINE.match(line.strip())
        if not m:
            out["unparsed_lines"] += 1
            continue
        t = float(m.group("t"))
        if not (t0 <= t <= t1):
            continue
        n = int(m.group("tcp") or m.group("udp") or 0)
        if m.group("src") == self_ip and not _is_lan(m.group("dst"), lan):
            key = f'{m.group("dst")}:{m.group("dp")}'
            out["out_bytes_non_lan"] += n
            out["by_destination"][key] = out["by_destination"].get(key, 0) + n
        elif m.group("dst") == self_ip and not _is_lan(m.group("src"), lan):
            out["in_bytes_non_lan"] += n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--t0", type=float, required=True)
    ap.add_argument("--t1", type=float, required=True)
    ap.add_argument("--lan", default="192.168.4.")
    ap.add_argument("--self-ip", default="192.168.4.39")
    a = ap.parse_args()
    print(json.dumps(egress_summary(open(a.text), a.t0, a.t1, a.lan, a.self_ip), indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests; adjust the regex against three real lines from the Jetson's capture before trusting
  the summary** (tcpdump's `-q` format differs slightly between versions; the test lines are from tcpdump 4.99).

- [ ] **Step 5: Run the capture (procedure above), write EG1/EG2 verdicts into results section 5, delete the
  egress clause from section 7, rewrite DR-11's status to name what is verified now (container environment,
  `disable_active_learning` in every request, egress during one run) and what is not (a capture during a model
  pull).**

- [ ] **Step 6: Commit** `git commit -m "field-tests: egress captured during a full run, EG1/EG2 verdicts; DR-11 status"`.

---

### Task 7: Bridges honour `GUARDIAN_BIND` (reviewer's open item; needs D-a)

**Files:**
- Modify: `jetson/guardian-up.sh:11-14`, `jetson/guardian-status.sh` (print the bind), `docs/ARCHITECTURE.md` §7,
  `README.md` limitations, `docs/field-tests/RUNBOOK-2026-09-26-capture.md` (dated note: set `GUARDIAN_BIND=0.0.0.0`
  or tunnel `8765` and `9090` for a capture session).
- Test: `src/prevera_perception/test/test_guardian_up_bind.py` (create)

- [ ] **Step 1: Write the failing test** (structural: the script is read, not run)

```python
"""guardian-up.sh binds the bridges the way mjpeg_server.py binds the camera views: loopback unless GUARDIAN_BIND says otherwise."""
import re
import subprocess
from pathlib import Path

UP = Path(__file__).resolve().parents[3] / "jetson" / "guardian-up.sh"


def test_bridges_are_launched_with_the_bind_address():
    text = UP.read_text()
    assert 'BIND="${GUARDIAN_BIND:-127.0.0.1}"' in text
    assert re.search(r'foxglove_bridge_launch\.xml .*address:="\$BIND"', text)
    assert re.search(r'rosbridge_websocket_launch\.xml .*address:="\$BIND"', text)


def test_empty_guardian_bind_means_loopback():
    # the same shell expansion the script uses; an empty value must fall to the default
    out = subprocess.run(["bash", "-c", 'GUARDIAN_BIND=""; BIND="${GUARDIAN_BIND:-127.0.0.1}"; echo "$BIND"'],
                         capture_output=True, text=True).stdout.strip()
    assert out == "127.0.0.1"
```

- [ ] **Step 2: Run, expect the first test to fail**

- [ ] **Step 3: Edit `guardian-up.sh`** — after `export ROS_DOMAIN_ID=42`:

```bash
BIND="${GUARDIAN_BIND:-127.0.0.1}"   # loopback unless exposed on purpose; the OMEN capture sessions set 0.0.0.0 or tunnel
```

and append ` address:="$BIND"` to both `ros2 launch … port:=…` lines; the `echo "started"` line becomes
`echo "started (bridges bound to $BIND)"`. Keep `bash -n jetson/guardian-up.sh` green.

- [ ] **Step 4: Documents** — ARCHITECTURE §7: the exposure table row for the bridges becomes "loopback by default,
  `GUARDIAN_BIND=0.0.0.0` to expose"; README limitations: delete the "bridges still expose the camera topic"
  sentence; runbook: a dated note at the top, not an edit of the 09-26 steps.

- [ ] **Step 5: Run the test file, `bash -n`, the suite. Commit** `git commit -m "jetson: foxglove_bridge and rosbridge bind loopback unless GUARDIAN_BIND says otherwise"`.

---

### Task 8: `rf_eval.py` into the repo (needs D-b)

**Files:**
- Create: `jetson/rf_eval.py` (verbatim copy from the Jetson, `/opt/nvme/frames/rf_eval.py`, plus a 3-line header
  comment: what it was used for, on which date, that `f5_device_fit.py` supersedes it for cost measurements).
- Modify: `docs/field-tests/2026-09-27-rfdetr-results.md` section 7 ("`rf_eval.py` is on the Jetson only" → in the
  repo at this commit) and its Reproduce block; the Client row of the section-2 table.

- [ ] **Step 1: `scp jeremy@192.168.4.39:/opt/nvme/frames/rf_eval.py jetson/rf_eval.py`; `python3 -m py_compile jetson/rf_eval.py`.**
- [ ] **Step 2: Header comment; document edits. Commit** `git commit -m "jetson: rf_eval.py, the 09-27 runner, versioned (09-27 next step 4)"`.

---

### Task 9: Close-out documents, PR, tag

**Files:**
- Modify: `docs/field-tests/HANDOFF-2026-09-28.md` ("Review pass" deferred minors → closed with commit ids;
  "Next, in order" pruned), `docs/DECISIONS.md` DR-11 status and DR-17 evidence (the two pre-declared measurements
  of this plan, with commit times), `README.md` at-a-glance test count, `CITATION.cff` `date-released` = the tag
  date.

- [ ] **Step 1: Documents; suite; commit** `git commit -m "docs: gaps closed on 2026-09-28; handoff and decision records updated"`.
- [ ] **Step 2: Push and PR** (Jeremy's instruction for the push): `ALLOW_PUSH=1 git push -u origin gaps-2026-09-28`,
  `gh pr create --base main --title "Close the gaps: review minors, co-load and egress measured, bridges bound, runner versioned" --body-file ~/Downloads/PR3-close-the-gaps.md`; the body lists the nine tasks with their commit ids and the four verdicts (CL1, CL2, EG1, EG2), in the shape of PR #2's description.
- [ ] **Step 3: After CI and merge (merge commit):** `git checkout main && git pull && git tag -a v0.1.0 -m "v0.1.0" && ALLOW_PUSH=1 git push origin v0.1.0`.

---

## Not in this plan (on purpose)

- **Room-frame plan for the class split** (the top item in the handoff): its own pre-declared plan, written and
  committed before any run, with the child chosen (`e65db0` at 79 ms or `00ba18` at 125 ms) and the segment
  labels it scores against.
- **Keypoint rescore v2 on the Mac** (`probe-classes`, `check --plan v2`, `score --plan v2`): runnable now that the
  Mac is linked; a separate go, because its result feeds DR-13 and deserves its own note.
- **Step-9 label files for the 09-25 bags**: need the bags and Jeremy's confirmation of every bound.
- **PR #3072 follow-ups on the OMEN**.
- **HANDOFF-2026-09-27's stale camera URLs**: a dated record; left as is.

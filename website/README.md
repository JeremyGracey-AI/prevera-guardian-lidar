# Website

The public web page for PREVERA GUARDIAN+AI. It rewrites the earlier marketing site so that every statement matches
the evidence in this repository. It keeps the earlier visual design (palette, type, components).

| File | What it is |
|---|---|
| `index.html` | The page. One self-contained HTML file with inline CSS and a few lines of inline JavaScript, no build step. |
| `demo.html` | The earlier interactive **app UI concept**, copied from the previous site with two changes: a disclaimer banner under its header (fictional data, not connected to the detector, features not implemented, no fall prediction today), and a new head (title and description, canonical, favicon links, pinned production scripts with integrity hashes). The banner is that of [`demos/mobile-app-concept.html`](../demos/mobile-app-concept.html) with "in this repository" and "here" dropped; its back link points to `index.html` instead of the repository README. Its title and description now say "UI concept". `index.html` also labels it wherever it links to it. |
| `assets/blind-spot-B.jpg` | A byte-identical copy of [`docs/field-tests/2026-09-27-rfdetr/blind-spot-B.jpg`](../docs/field-tests/2026-09-27-rfdetr/blind-spot-B.jpg). |
| `assets/logo.png` | The PREVERA GUARDIAN+AI logo, decoded from the base64 PNG embedded in the previous site (the same image in its nav and footer) and cropped to its visible area. The page shows it on a white chip, because its dark lettering disappears on the navy background. |
| `.vercelignore` | Keeps `README.md` and `NOTES.local.md` out of a Vercel deploy of this directory. |
| `favicon.svg`, `favicon-32.png`, `favicon.ico`, `apple-touch-icon.png` | The four icon files both pages link at the site root. Byte-identical to the files the previous site served (sha256 compared on 2026-09-29). |

## How to view it

Open `index.html` in a browser. It needs no server. To serve it locally instead:

```bash
cd website && python3 -m http.server 8000   # then open http://localhost:8000/
```

### External requests

- `index.html` loads the Inter and JetBrains Mono fonts from Google Fonts, as the previous site did. This is its only
  third-party request. It has no scripts from other sites, no analytics and no trackers. If the fonts are
  unreachable, the page falls back to system fonts.
- `demo.html` loads React 18.3.1, ReactDOM 18.3.1 (production builds) and `@babel/standalone` 7.29.9 from `unpkg.com`.
  Each script tag pins the exact version and carries an `integrity` (sha384) hash and `crossorigin="anonymous"`,
  so a changed file is refused by the browser. JSX is still compiled in the browser by Babel.
- The page's URL is https://preveraguard.com/: `canonical` and `og:url` point there. `og:image` is left out until an
  image exists that does not carry the old site's prediction claim. No Twitter card tags are set.

## Deploying

The page is static: no framework and no build step. It is meant to be served at https://preveraguard.com/ from a
new Vercel project with this directory as its root.

- Deploy `index.html`, `demo.html`, `assets/` and the four favicon files. `.vercelignore` keeps `README.md` and
  `NOTES.local.md` out of the deploy. On any other host, upload only those files.
- The footer says "No analytics or trackers". That stays true only while the host injects none: on Vercel, Web
  Analytics and Speed Insights must be off for the project.
- State on 2026-09-29, before the move: the domain is still served by the old site on another host (see the claims
  table). Creating the project, deploying and changing DNS are the owner's actions.

## Rules the page follows

- **Every number is either measured or cited.** Measured numbers trace to a file in this repository. Context numbers
  cite a named primary source with a link; each one was fetched and checked on 2026-09-27. The table below lists
  both kinds.
- **No placeholder remains.** The ask card states the ask and nothing else.
- **Detection today, prediction next.** The page says nothing predicts falls yet. Prediction appears as the goal the
  raise funds (roadmap column 2 and the ask card), always marked as not built.
- **The V-JEPA stage is a black box.** The page names it only as the proprietary verification stage that is not
  public. It gives no model, training, thresholds, latency or architecture (DR-15, NOTICE).
- **Wording for the results.**
  - "Flagged", never "alerted": the 4 of 6 are OBSERVE events (level 1).
  - The fixes are "tested offline, not enabled". The fixed configuration's time-to-WARN (0.7 to 4.0 s after onset;
    3.3 to 6.5 s on stillness alone) appears only with "offline replay" and "not yet live" (hero) or as a replay
    under "tested offline and not yet enabled" (evidence section 3), and cites the
    [fixed-config replay](../docs/field-tests/2026-09-27-fixed-config-replay.md). The first draft of this page left the figure out, because it was not yet in the
    repository, and repeated the repository's claim that only the 4 s rule could fire; the replay corrected both.
  - Privacy is stated as what the captures show: the client posts only to localhost; in the captured run the
    166 MB of frames went to the local server and 13 KB left the device (one run, one model, cameras off, no model
    download captured); an aggregated usage record still leaves, by decision. It is never stated as "frames never
    leave the device", and the camera path is never described as live: it is not in the alert path.
  - Every privacy number carries its scope: one run, one model, cameras off, no model download captured.
  - The list of fields that leave the device appears once, in the Known limitations item, with its source: the
    Inference 1.7.2 code, since the captures cannot read TLS.
  - The fine-tune is "on public data": 73 test images, one training run, near-duplicate frames not checked. The
    architecture search ran on one dataset (arm A, 736 images); arms B and C were plain RF-DETR nano comparison
    arms. The room-frame result (section 9) is one subject, one room, one camera of two, and says so.
  - Dates are PDT. Evidence section 8 notes once that the repository dates the last three captures 2026-09-29 UTC.
- **No regulatory claims.** "Path toward HIPAA-aligned deployment" appears only as a future item on the roadmap.
- **Out of the page:** patent docket numbers, filing dates, phone numbers, and customers or partners.
- **Contact** is the author's email and the GitHub repository only.

## Claims table

Paths are relative to the repository root, and line numbers refer to commit `72c25ac`, except the rows of the last
table (section 9), which refer to the merge of pull request 8 (2026-09-29). `demo.html` means
`website/demo.html` as it is in this directory. "One subject, one room, one session" applies to every measured LIDAR
and stock-camera result (README.md:10, 97-99, 314-315). The fine-tune results are on a public test split and carry
their own caveats in the last table.

### Status and identity

| Claim on the page | Evidence |
|---|---|
| Research prototype, measured on one subject in one room; not a medical device; not cleared by any regulator; not to be relied on to detect falls | README.md:10-11 |
| Apache-2.0; patent pending (no application number or date given) | README.md:11, 364-367; NOTICE:4-7 |
| The proprietary V-JEPA verification stage is not public, is shown only as a black box, and is not measured here | README.md:6-7; NOTICE:6-11; docs/DECISIONS.md:440-455 (DR-15) |
| ALERT and CRITICAL are defined but never emitted; this repository emits only levels 1 (OBSERVE) and 2 (WARN) | docs/ARCHITECTURE.md:31, 122, 127-129; docs/DECISIONS.md:451 |
| The target setting is senior-care rooms | README.md:3 |
| "Prevention + awareness" as the origin of the name (the page states that prevention is the long-term aim, and that the prototype only detects) | Old site's mission heading; README.md:3-8, 361-362 (detection only) |
| Built with Claude Code as a collaborator; Jeremy Gracey ran the hardware, made every decision and owns the results | README.md:369-373 |
| Contact jeremy.a.gracey@gmail.com and github.com/JeremyGracey-AI/prevera-guardian-lidar | README.md:248, 377-378 |
| The UI concept (`demo.html`) uses fictional data apart from the author's own name on its Profile screen, and it is not connected to the detector; the features it shows are not implemented | demo.html:156-186 (the `// Mock Data` block), 718 (the Profile screen); demos/README.md:7-10 (the same statement for the public concept) |
| The page's address is https://preveraguard.com/ (`canonical`, `og:url`) | README.md:377; the page served at that address on 2026-09-29 carries the same `canonical` and `og:url` |
| On 2026-09-29, before the move, the domain was still served by the old site | `curl -sI https://preveraguard.com/` on 2026-09-29: `server: LiteSpeed`, `platform: hostinger`, `last-modified` 2026-05-07 |

### Hardware and pipeline

| Claim on the page | Evidence |
|---|---|
| RPLIDAR C1, 2D, 10 Hz, on the floor, scan plane about 2 cm, level (gauge 0.0°) | README.md:59; docs/ARCHITECTURE.md:14; docs/field-tests/2026-09-27-floor-mount-grid.md:3, 11; docs/DECISIONS.md:131 |
| Finds a person lying down from geometry alone, with no images (LIDAR path) | README.md:3-4 |
| Logitech C920 on the counter, 98 cm, 15° down; Logitech Brio 100 on the floor, 4 cm, level | docs/DECISIONS.md:303; docs/ARCHITECTURE.md:15-16; docs/field-tests/2026-09-27-rfdetr-eval-plan.md:9-10 |
| Jetson Orin Nano 8 GB, JetPack 6.2.1, ROS 2 Humble | docs/ARCHITECTURE.md:19; docs/field-tests/2026-09-27-rfdetr-results.md:53 |
| Pipeline: background model (rolling median + foreground hold), DBSCAN clustering with PCA shape, nearest-centroid tracker, fall heuristic (elongated and person-sized; a spike then stillness, or sustained down), `/fall_events` OBSERVE and WARN | README.md:57-76; docs/ARCHITECTURE.md:11-47 |
| Camera streams at 1280×720, 30 Hz, recorded alongside the LIDAR in rosbag2 bags; the 09-27 camera record is the original sqlite3 bag, and bags are recorded as mcap from now on (DR-16); frames extracted at 1 fps for evaluation. (docs/ARCHITECTURE.md:23 shows the go-forward mcap policy, not what happened on 09-27.) | docs/ARCHITECTURE.md:123-124; docs/field-tests/2026-09-27-floor-mount-grid.md:87-89; docs/DECISIONS.md:461-473; docs/field-tests/2026-09-27-rfdetr-results.md:38 |
| Roboflow Inference 1.7.2 on the Jetson, listening on 127.0.0.1:9001 only; stock COCO RF-DETR with no fine-tuning; evaluated offline; not in the live alert path | docs/field-tests/2026-09-27-rfdetr-results.md:41-55; docs/DECISIONS.md:297-305, 338-339 |
| Fusion (D0): where it runs is open, and nothing is built | docs/DECISIONS.md:420-438; README.md:203, 320 |
| The camera half of D0 exists as a time-on-floor Roboflow Workflow (seconds since a down-pose track entered a floor zone); validated structurally; ran once on the hosted API on one public image, which shows only that it executes; not run on video | docs/DECISIONS.md:435-438; docs/field-tests/2026-09-28-roboflow-finetune-results.md:407-410; tools/roboflow/README.md:59-66 |
| D1 open: box shape no (C3); keypoints await the v2 rescore; a fine-tuned class split passed F1/F2 on public data, and on room frames from the counter camera (section 9). The first keypoint run was invalid and not scored | docs/DECISIONS.md:60, 394-396 (at `72c25ac`; the room clause: section 9 rows); docs/field-tests/2026-09-27-rfdetr-keypoints-status.md:1-5, 27-29 |
| Keypoint rescore plan v2: written 2026-09-28, fixes the class rule, not run | docs/field-tests/2026-09-28-rfdetr-keypoints-plan-v2.md:1-3, 8-11; docs/DEVELOPMENT-LOG.md:112 |
| Either D1 option needs a counter-camera view that shows the whole body; what follows from the room-frame result is open | docs/DECISIONS.md:416-418 (at `72c25ac`); section 9 rows |
| A hosted inference API was rejected because frames would leave the room | docs/DECISIONS.md:334-337 (DR-11) |
| On 2026-09-27 the client posted only to localhost and privacy was reported, not verified; the server was also posting a record of every request once a minute, and `TELEMETRY_OPT_OUT` does nothing in Inference 1.7.2 (by the 1.7.2 code; the capture cannot read TLS) | docs/field-tests/2026-09-27-rfdetr-results.md:73-94; docs/field-tests/2026-09-28-roboflow-finetune-results.md:249-252, 266-271; docs/DECISIONS.md:343-351 |
| Camera inference was evaluated offline: in the RF-DETR box evaluation, inference ran on the Jetson; frames were then copied to a Mac for scoring; the keypoint preview ran on the Mac CPU | docs/DECISIONS.md:57 (DR-10); docs/field-tests/2026-09-27-rfdetr-results.md:91-93; docs/field-tests/2026-09-27-rfdetr-keypoints-status.md:15-17 |
| Privacy framing: the LIDAR uses no images; the webcams were tested with a detector on the device; the claim is "inference on the device, frames posted only to localhost", checked by four network captures (two egress, two container start); the usage record leaves by decision; a model download has never been captured | docs/DECISIONS.md:58, 309-310, 317-333 |
| The camera views are unauthenticated; since 2026-09-28 they bind the loopback address by default and are opened through an ssh tunnel; exposing them is an explicit setting for a trusted bench; the camera topic stays reachable to anyone who can join the ROS domain | README.md:337-341; docs/ARCHITECTURE.md:205-217 |
| Furniture feet look like a lying person at floor level (the main false-alarm risk once stillness works) | README.md:321-322; docs/field-tests/2026-09-27-floor-mount-grid.md:47-49 |
| Stack tags: Python 3.10 (the Jetson's Python floor, enforced by the tests), DBSCAN, mcap, pytest | docs/DECISIONS.md:187-202; README.md:63, 245; docs/DECISIONS.md:467 |
| Stack tags: RF-DETR (fine-tuned, public data), Roboflow Train (NAS) + Model Evaluation, tcpdump | docs/field-tests/2026-09-28-roboflow-finetune-results.md:3-6, 26, 213-214 |
| The problem framing: notice a person on the floor while keeping images of them in the room; a standing person is a small slice, a person on the floor a long thin one | README.md:35-36 |
| The hero schematic (segments A and B, with a 1 m range ring) is an illustration drawn from the floor-trial numbers, not live data, and the page labels it so | docs/field-tests/2026-09-27-floor-mount-grid.md:61-62; docs/field-tests/2026-09-27-rfdetr-results.md:194-201 |
| The tests run with no ROS and no hardware | README.md:243-255 |
| The process: every evaluation is written down before it runs, replayed, audited and closed with a decision record; the runbook uses tape and angle-gauge measurements and labels typed per phase; goldens come before the change | README.md:80-82; docs/PROCESS.md:18-64 |
| Labels failed twice and were reconstructed from the camera frames; the label window is now tested before recording | docs/field-tests/HANDOFF-2026-09-27.md:99-101; docs/PROCESS.md:45-47 |
| The adversarial audits were run with Claude Code, not an external reviewer | README.md:371-372 |
| AI governance: a pre-push hook blocks pushes unless explicitly allowed; the sudoers scope on the Jetson allows service control, clocks, a power-mode query and shutdown | docs/DECISIONS.md:482-488; docs/PROCESS.md:91-105 |
| The audit found "frames never leave the device" wrong as written, and it was corrected to "the client posted only to localhost" | docs/field-tests/2026-09-27-rfdetr-results.md:91-95; docs/PROCESS.md:72-75 |
| On 2026-09-28 the fine-tune plan preceded its results by 2 h 41 min, and every network capture had its bars committed before it ran | docs/DECISIONS.md:492-494; docs/PROCESS.md:30-32; docs/field-tests/2026-09-28-roboflow-finetune-results.md:213-214, 282-286, 352-353, 376-377; docs/field-tests/2026-09-28-egress-recapture-plan.md:3; docs/field-tests/2026-09-29-version-check-capture-plan.md:3; docs/field-tests/2026-09-29-yolo-offline-capture-plan.md:3 |
| What the process caught on 2026-09-28: the first capture failed its bar and the bar stayed; the second capture showed the first had started 34 s late, and the correction is written beside the result; a start-up check failed because its bar was wider than the switch under test, and the probe it caught was switched off and verified by a fourth capture | docs/field-tests/2026-09-28-roboflow-finetune-results.md:234, 253-260, 360-369, 383-385 |

### Measured results

| Number on the page | Evidence |
|---|---|
| Original mount: the scan toward the fall spot matched the empty room for 50 s | README.md:105; docs/DECISIONS.md:120-121 |
| Lowered mount: extent 0.8 to 1.3 m, stillness peaked at 0.4 s, no WARN | README.md:106 |
| Counter, level, 121 cm: lost a person on the floor for 39 s; 0 false alarms in 165 s | README.md:40-41, 107; docs/DECISIONS.md:122-123 |
| Floor, about 2 cm: 4 of 6 lie-downs (A, C, D, E) flagged within about a second, at every range tried (1.3 to 2.6 m) | docs/field-tests/2026-09-27-floor-mount-grid.md:61-65, 71-72; docs/DECISIONS.md:132-134 |
| Segment A: events from 28.9 s for a segment that starts at 28 s | docs/field-tests/2026-09-27-floor-mount-grid.md:61 |
| Both misses were end-on (B feet first, F head first); the plane saw 0.22 to 0.33 m of soles or head | docs/field-tests/2026-09-27-floor-mount-grid.md:62, 66, 72-75; README.md:42-45, 115, 119 |
| Floor-trial table: A 2.0 m, 1.64 m, 350 OBSERVE · B 0.9 m, 0.33 m, none · C 2.6 m, 1.62 m, one WARN at 165.3 s then silent 26 s · D 1.6 m, 0.99 m, 347 OBSERVE · E 1.3 m, 0.92 m, 335 OBSERVE · F 0.83 m, 0.22 m, none · W 0 false alarms | README.md:112-120; docs/field-tests/2026-09-27-floor-mount-grid.md:59-67 |
| Segment C's single WARN was triggered by a jitter-made speed spike (1.53 m/s from a 15 cm centroid jump) | docs/DECISIONS.md:241-242 (DR-07) |
| Across or diagonal clusters 0.9 to 1.65 m | docs/field-tests/2026-09-27-floor-mount-grid.md:71 |
| 0 false alarms in 95 s of walking | docs/field-tests/2026-09-27-floor-mount-grid.md:67, 81-82; README.md:108, 120 |
| 1,131 of 1,132 events were OBSERVE; the one WARN is segment C's | README.md:122-124; docs/field-tests/2026-09-27-floor-mount-grid.md:116-118 (erratum) |
| Stillness never exceeded 3.4 s, although each lie-down was held for about 30 s | README.md:46, 122-123; docs/field-tests/2026-09-27-floor-mount-grid.md:76-78 |
| Grid walk: continuous tracking at all six stations, zero dropouts, zero fall events | docs/field-tests/2026-09-27-floor-mount-grid.md:44 |
| Incident hold on replay: C holds WARN to 193 s; every other segment unchanged; the walking baseline had 0 WARN either way | README.md:130; docs/DECISIONS.md:238-243 |
| Windowed stillness: 0.25 m over 1.5 s; 12 stillness unit tests, including a boundary test | README.md:131; docs/DECISIONS.md:279-287 |
| Without `min_range_m` 0.3, the fixed config turns a 6 cm clutter track into a WARN at 24 s | README.md:132; docs/DECISIONS.md:281-283 |
| Speed gate motivated by 4.6 m/s "motion" that was association jumps | README.md:133; docs/DECISIONS.md:250-251 |
| Default config byte-identical to the incident-hold commit on all 7 bags; legacy goldens pass (`test_legacy_defaults_unchanged`) | docs/DECISIONS.md:219-222; docs/DEVELOPMENT-LOG.md:87 |
| Fixed config replayed on `floor-trials-1` (hero, evidence section 3, roadmap item 1): WARN 0.7 to 4.0 s after onset in A, C, D and E; 3.3 to 6.5 s on stillness alone; 0 events walking or standing; the fast WARNs come from the spike rule, set off by centroid jitter in three of the four; spot memory and spike memory come before the flip | docs/field-tests/2026-09-27-fixed-config-replay.md:42, 47, 54-55 (result), 60-74 (caveats 1 and 2); README.md:348-349 (spot memory and spike memory before the flip) |
| `min_range_m` is 0.05 on the device today and is raised to 0.3 at the flip (a parameter value, not a switch) | docs/ARCHITECTURE.md:137; docs/DECISIONS.md:268-269 |
| 38 → 70 passing tests (1 skipped each time), from the replay harness to windowed stillness | docs/DEVELOPMENT-LOG.md:33, 36 |
| 130 passed, 1 skipped at main `6990dfe`; the skip needs ROS (`rclpy`) | README.md:24, 254; docs/DEVELOPMENT-LOG.md:40-42; CI run 36521147716 on `6990dfe` (success) |
| The pre-declared bars that decide the switch have not been run; the device still runs the legacy detector | README.md:49-50, 137-138, 316-319 |
| RF-DETR plan committed at 16:38 PDT, results at 17:26 PDT (2026-09-27); keypoint plan at 17:36, run at 17:44 | docs/DECISIONS.md:490-491; docs/DEVELOPMENT-LOG.md:88-90 (commit times, local); docs/field-tests/2026-09-27-rfdetr-results.md:14-15 (UTC to PDT) |
| Counter C920: person in 33/33 B frames and 30/30 F frames, for nano, base and medium, at conf ≥ 0.4 | docs/field-tests/2026-09-27-rfdetr-results.md:19-21, 123, 125 |
| Floor Brio: B 33/33; F 26/30 (nano), 20/30 (base), 30/30 (medium) | docs/field-tests/2026-09-27-rfdetr-results.md:124, 126 |
| Walking: 90/90 on the counter camera, for all three sizes; the boxes are hips and legs only | docs/field-tests/2026-09-27-rfdetr-results.md:21, 115, 144-145 |
| C3 failed: median box width/height 0.78 to 0.87 in B, D and E; keypoints next | docs/field-tests/2026-09-27-rfdetr-results.md:23-25, 159-162, 180 |
| Round trip: nano 107.9 ms (9.3 fps); base and medium 126.9 ms (7.9 fps). These are median serial client round trips with one request in flight and the cameras stopped, not a throughput benchmark | docs/field-tests/2026-09-27-rfdetr-results.md:27-29, 236-244 |
| Lowest `MemAvailable` 2,584 MB (medium run, two models resident, cameras off) | docs/field-tests/2026-09-27-rfdetr-results.md:30, 257-258 |
| Whether inference disturbs the LIDAR under load: measured once on 2026-09-28 with a fine-tuned model. CL1: 594 scans against 567 idle (+4.8%), pass. CL2: 0 gaps over 0.5 s (largest 0.105 s), pass. Both recordings 10.009 Hz; bars committed before the recording; one run of one model, cameras off; `/fall_events` silent, nobody asked to be in the room | docs/field-tests/2026-09-28-roboflow-finetune-results.md:186-189, 194-211; docs/DECISIONS.md:369-371 |
| 580 frames, 1 fps; frames within a segment are near-duplicates | docs/field-tests/2026-09-27-rfdetr-results.md:32-33, 38 |
| Blind-spot figure numbers (t = 110 s; clusters 0.31 m and 0.28 m; person 0.93 and 0.92; 33/33 on each camera; 0 events); the hero schematic labels them "two ~0.3 m clusters (soles)" | docs/field-tests/2026-09-27-rfdetr-results.md:190-204; README.md:28-31 |
| The published figure was re-encoded once for publication (JPEG quality 92, metadata stripped) | docs/field-tests/2026-09-27-rfdetr-results.md:357 |
| 18 decision records (DR-00 to DR-17), each with its status, the options on record (or a note that none were written down) and its evidence; the open ones say what comes next | README.md:192-193; docs/DECISIONS.md:45-64 (index); docs/DECISIONS.md:420-438 (DR-14), 476-500 (DR-17); a per-record field check on 2026-09-27 found Status, options (DR-12 labels the field "Options") and Evidence in all 18 records, no Context or Consequences in DR-14, and no Context in DR-17 |
| roboflow/inference#3072: one ENV line sets `TRITON_CACHE_DIR` in the JetPack 6.2.0 image, plus a unit test; HTTP 500 before, predictions from all three RF-DETR sizes after; verified with the variable set at runtime, image not rebuilt; **open, review required, as of 2026-09-29** | README.md:306-310; docs/DECISIONS.md:374-387; `gh pr view 3072 -R roboflow/inference` on 2026-09-29: state OPEN, reviewDecision REVIEW_REQUIRED, mergedAt null, +23/−0, 2 files, updatedAt 2026-09-28T04:47:14Z |
| Not public: the V-JEPA stage, raw recordings, extracted frames, model predictions on room frames, and the packet captures | README.md:342; NOTICE:9-11; docs/PROCESS.md:119-120; docs/field-tests/2026-09-28-roboflow-finetune-results.md:171-174, 219-220, 291-292 |
| Public since 2026-09-28: the on-device runners (`jetson/rf_eval.py`, `jetson/f5_device_fit.py`), the container command (`jetson/inference-server-up.sh`), the fine-tune plan and results, Roboflow's evaluation extracts and the network-capture summaries (no frames), and the time-on-floor Workflow | README.md:219-221, 343-344; docs/field-tests/2026-09-28-roboflow-finetune-results.md:136-140, 216-219; docs/DEVELOPMENT-LOG.md:123, 126 |
| Roadmap column 1 (items 1 to 6) | README.md:348-360 |
| Roadmap column 2 (supervised pilots, then prediction) is the founder's funding ask, not part of the repository's roadmap; prediction is stated as not built | See "Founder's stated ask" below |
| Roadmap, "Later: not built": WiFi sensing as a camera-free modality. Not built and not measured | No source in this repository. It is the owner's stated direction (2026-09-29), listed as an intention and not as a result |

### Fine-tune, device fit and network captures (2026-09-28 PDT)

| Number or statement on the page | Evidence |
|---|---|
| The data is public: three Roboflow Universe datasets, forked unchanged; no frame from the test room was uploaded, trained on or scored | docs/field-tests/2026-09-28-roboflow-finetune-plan.md:12, 17-19; docs/field-tests/2026-09-28-roboflow-finetune-results.md:6 |
| The architecture search ran on one dataset (arm A, 736 images), 1 h 59 min; arms B and C were plain RF-DETR nano comparison arms; every model was trained and scored on Roboflow | docs/field-tests/2026-09-28-roboflow-finetune-results.md:26-28, 104; README.md:177-179; docs/field-tests/2026-09-28-roboflow-finetune-plan.md:29-34 |
| The plan was committed at 11:30 PDT on 2026-09-28, before any training started | docs/field-tests/2026-09-28-roboflow-finetune-results.md:3-4; docs/PROCESS.md:30-32; docs/DEVELOPMENT-LOG.md:111 |
| F1: `lying` 1.000 / 1.000 against a bar of 0.90 each, at the valid split's threshold 0.75, not tuned on test | docs/field-tests/2026-09-28-roboflow-finetune-results.md:61, 84; docs/field-tests/2026-09-28-roboflow-finetune-plan.md:37-45 |
| F2: 0 of 24, bar 5% of the 24 lying instances, swaps counted both ways; read at 0.70 and 0.80, which agree | docs/field-tests/2026-09-28-roboflow-finetune-results.md:43-45, 71-80, 85; docs/field-tests/2026-09-28-roboflow-finetune-plan.md:46-49 |
| F3: `bed` and `lying` confused 0 times either way (16 bed, 24 lying); `bed` labels the furniture | docs/field-tests/2026-09-28-roboflow-finetune-results.md:76-77, 86, 411-413 |
| F4: URFD frames `fall` 0.931 / 0.982, 0 swaps in 110; lying3 `lying` 0.910 / 0.950, 4 swaps in 299; report only, swaps read at 0.40 | docs/field-tests/2026-09-28-roboflow-finetune-results.md:43-45, 108-109, 124-125 |
| 73 test images, 89 instances (24 lying, 11 sitting), one dataset of one author's rooms; "not dead on arrival", not a recall estimate | docs/field-tests/2026-09-28-roboflow-finetune-results.md:17-20 |
| An upper bound: near-duplicate frames between train and test not checked; one scored run per arm; arm B ran twice by accident and the duplicate moved test mAP@50 by 0.006 | docs/field-tests/2026-09-28-roboflow-finetune-results.md:33-37, 417-421 |
| Errors on the upright side: 4 standing read as sitting, 1 missed, 0 false positives; `lying` 1.000 / 1.000 at every stored threshold from 0.11 to 0.87 | docs/field-tests/2026-09-28-roboflow-finetune-results.md:79-80, 89-93 |
| Two evaluators: 96.85 (the search's own valid mAP@50-95) and 0.963 (Model Evaluation, same split); whether the rule would pick the same model under Model Evaluation is not known | docs/field-tests/2026-09-28-roboflow-finetune-results.md:55-59, 422-424 |
| Arm C's splits were rebalanced to 70/20/10 before versioning; its fork had 6 test images | docs/field-tests/2026-09-28-roboflow-finetune-plan.md:19; docs/field-tests/2026-09-28-roboflow-finetune-results.md:28 |
| Licences: datasets CC BY 4.0 as their Universe uploaders state, URFD copy not checked against the original terms; trained models under PML-1.0 | docs/field-tests/2026-09-28-roboflow-finetune-plan.md:12-13; docs/field-tests/2026-09-28-roboflow-finetune-results.md:444-445, 463-464, 475-476 |
| Not a room result; the predictions in the cost runs were discarded by design; the room frames were scored a day later under their own plan (section 9) | docs/field-tests/2026-09-28-roboflow-finetune-results.md:171-174, 446; section 9 rows |
| F5 ran at 15:54 PDT (22:54 UTC): 580 room frames, one request at a time, to 127.0.0.1:9001 only, cameras off | docs/field-tests/2026-09-28-roboflow-finetune-results.md:132-135, 182 |
| Fast child `e65db0`: 288×288, 78.7 ms, 12.7 fps. The rule's pick `00ba18`: 640×640, 125.2 ms, 8.0 fps | docs/field-tests/2026-09-28-roboflow-finetune-results.md:144-145 |
| Stock nano 107.9 ms, 9.3 fps (input not read); stock base 560×560, 126.9 ms, 7.9 fps; measured 2026-09-27 the same way | docs/field-tests/2026-09-28-roboflow-finetune-results.md:132-133, 146-147 |
| The fast child is 27% faster than stock nano; the rule's pick costs what stock base and medium cost | docs/field-tests/2026-09-28-roboflow-finetune-results.md:152-154 |
| Lowest `MemAvailable` with both resident 2,799 MB; only the minimum is usable; cameras off, so capture load is absent | docs/field-tests/2026-09-28-roboflow-finetune-results.md:159-163 |
| First call 17.5 s for a model not yet in the cache; 1.8 s with the weights already cached; that download has never been captured | docs/field-tests/2026-09-28-roboflow-finetune-results.md:168-170, 279-280, 313-315 |
| F5 is report only, with no bar; serial, one request in flight; the Jetson's ROS checkout was `fix/background-absorption`, not `main` | docs/field-tests/2026-09-28-roboflow-finetune-plan.md:54-58; docs/field-tests/2026-09-28-roboflow-finetune-results.md:87, 182-183, 430-431 |
| Four captures, each against bars committed before it ran; in PDT all four fall on 2026-09-28; the repository dates the last three 2026-09-29 UTC | docs/field-tests/2026-09-28-roboflow-finetune-results.md:213-215, 282-288, 352-355, 376-379; docs/PROCESS.md:83; docs/DEVELOPMENT-LOG.md:122, 127, 130, 132 |
| Capture 1, EG1 FAIL: 285,098 bytes against a bar of under 200,000, almost all one 280 KB post to api.roboflow.com; the bar was not moved | docs/field-tests/2026-09-28-roboflow-finetune-results.md:234-236; docs/field-tests/2026-09-28-egress-recapture-plan.md:24 |
| Capture 1 started 34 s late and saw 167 of the 580 frames, so 285,098 is a lower bound; the correction is written beside the result | docs/field-tests/2026-09-28-roboflow-finetune-results.md:253-260 |
| Until `METRICS_ENABLED=False` was set on the evening of 2026-09-28 (PDT), during every run of 2026-09-27 and 2026-09-28 the server posted, once a minute, a record of every request; no frames and no boxes; `TELEMETRY_OPT_OUT=True` does nothing in Inference 1.7.2; by the code, TLS not read | docs/field-tests/2026-09-28-roboflow-finetune-results.md:245, 249-252, 266-271, 282-288 (the switch set, before the 01:09 UTC run of 2026-09-29, which is 18:09 PDT on 2026-09-28) |
| Capture 2, EG1 pass: 12,987 bytes, about 2.4 KB every ~10 s to api.roboflow.com, with `METRICS_ENABLED=False` | docs/field-tests/2026-09-28-roboflow-finetune-results.md:301, 310-313 |
| EG2 passed in captures 1 and 2; VC2 passed in captures 3 and 4, first answer seen at 100 s and at 45 s, both counted from the server process start; in capture 3 the exact moment of the first answer was not captured | docs/field-tests/2026-09-28-roboflow-finetune-results.md:261, 307, 370-372, 386; docs/field-tests/2026-09-29-version-check-capture-plan.md:24-27; docs/field-tests/2026-09-28-roboflow/version-check-capture.json:23-25; docs/field-tests/2026-09-28-roboflow/yolo-offline-capture.json:22-23 |
| In capture 2 the full 166 MB of frames went to the local container and 13 KB left the device; one run, one model, cameras off; the model was already on the device, so no download was captured | docs/field-tests/2026-09-28-roboflow-finetune-results.md:287-288, 313-315, 346-350 |
| Capture 3, VC1 FAIL: no GitHub traffic, but two 0-byte handshakes to 1.1.1.1:80, the online check of the ultralytics package by its code; no request sent | docs/field-tests/2026-09-28-roboflow-finetune-results.md:352-369 |
| Capture 4, VC1 pass: no packet from the container to any non-LAN address in 32.6 minutes; no request sent | docs/field-tests/2026-09-28-roboflow-finetune-results.md:376-385 |
| A container that is not asked anything sent nothing to any non-LAN address for the 32.6 minutes it was watched; a model download has never been captured | docs/field-tests/2026-09-28-roboflow-finetune-results.md:394-396; docs/DECISIONS.md:329-331, 366-367; README.md:183-186 |
| What still leaves while inferring: about 2.4 KB every ~10 s to api.roboflow.com, an aggregated usage record with no image and no per-detection field | docs/DECISIONS.md:357-360; docs/field-tests/2026-09-28-roboflow-finetune-results.md:321-327 |
| The fields, stated once under Known limitations. Before the switch: class and confidence per detection, API key, hostname, IP, MAC. Still leaving: API key in clear, hashed hostname and IP, counts. From the Inference 1.7.2 code; the captures cannot read TLS | docs/field-tests/2026-09-28-roboflow-finetune-results.md:238-252, 266-271, 321-327; docs/DECISIONS.md:318-324, 356-360; README.md:323-330 |
| Whether the usage record may leave was a product decision: yes, for now (Jeremy Gracey, DR-11); no revisit trigger is set | docs/DECISIONS.md:332-333; README.md:335-336 |
| Roadmap, privacy item: active learning off in every request; the container environment versioned; the pingback, the version check and the start-up probe each switched off and verified by capture; left: a capture that covers a model download | README.md:355-358; docs/DECISIONS.md:344-346; docs/field-tests/2026-09-28-roboflow-finetune-results.md:180, 390-396; jetson/inference-server-up.sh:12-28 |
| The container command and its switches | jetson/inference-server-up.sh:39-51 |
| `demo.html` loads React 18.3.1, ReactDOM 18.3.1 and `@babel/standalone` 7.29.9 from unpkg.com, pinned, with integrity hashes | demo.html:13-15; each hash recomputed from the CDN response on 2026-09-29 |

### External context (fetched and checked 2026-09-27)

| Number on the page | Source | Caveat stated on the page |
|---|---|---|
| Over 43,000 deaths from falls among adults 65+ in 2024; the leading cause of injury death for that group | CDC, [About Older Adult Fall Prevention](https://www.cdc.gov/falls/about/index.html) (WISQARS; page updated 2026-09-04) | US, 2024 |
| 14 million (27.6%) older adults reported falling during the previous year, 2020 | Kakara et al., [MMWR 2023;72:938-943](https://www.cdc.gov/mmwr/volumes/72/wr/mm7235a1.htm) | Self-reported (BRFSS); excludes people in long-term care facilities, "who are at higher risk for falls" |
| US$80.0 billion healthcare spending on non-fatal falls among older adults, 2020, "with the majority paid by Medicare" | Haddad et al., Inj Prev 2024;30(4):272-276, [PubMed 39029927](https://pubmed.ncbi.nlm.nih.gov/39029927/) (abstract read through NCBI E-utilities `efetch`, rechecked 22:10 PDT 2026-09-27) | Non-fatal falls only; 2020 |
| People over 90: 80% (53/66) of those who fell could not get up after at least one fall; 30% (20/66) lay on the floor for an hour or more; lying long was strongly associated with serious injury, hospital admission and moves into long-term care | Fleming and Brayne, BMJ 2008;337:a2227, [PubMed 19015185](https://pubmed.ncbi.nlm.nih.gov/19015185/) | UK cohort, n = 110, own homes or care homes; not a US or facility rate |

### Founder's stated ask (not a measurement)

| On the page | Source |
|---|---|
| $500K per site for supervised pilots at 2 to 3 selected sites, at most $1.5M for three; prediction as the goal the raise funds, not built | The founder's ask. It is not in the repository, and the page labels it as an ask, not as a result or a projection. |

### Section 9: the fine-tuned model on room frames (rows added 2026-09-29, lines at the merge of pull request 8)

| Claim on the page | Source |
|---|---|
| Scored on 2026-09-29 on the 580 recorded room frames, on the Jetson, at confidence 0.56; one run, scored once, 580 answered, no request error | docs/field-tests/2026-09-29-room-frames-results.md:32-37 |
| The device-sized model: the faster of the two in section 7, and not the one that passed F1 and F2 | docs/field-tests/2026-09-29-room-frames-plan.md:33-37; docs/field-tests/2026-09-29-room-frames-results.md:95 |
| Plan, runner and scorer pushed to the public repository before the run | docs/field-tests/2026-09-29-room-frames-results.md:32; docs/field-tests/2026-09-29-room-frames-plan.md (commits `560006a`, `2f39402`) |
| R1: one camera reads `lying` in >= 80 % of B and of F, same camera; pass, counter camera 32 of 33 and 30 of 30 | docs/field-tests/2026-09-29-room-frames-results.md:19; docs/field-tests/2026-09-29-room-frames-plan.md:89-93 |
| R2: counter camera reads `lying` in <= 5 % of 90 walking frames; pass, 0 of 90 | docs/field-tests/2026-09-29-room-frames-results.md:20; docs/field-tests/2026-09-29-room-frames-plan.md:94-96 |
| Floor camera: B 32 of 33; F 0 of 30, all 30 read `standing`; would fail R1 alone | docs/field-tests/2026-09-29-room-frames-results.md:23, 64 |
| Floor camera in the diagonal segments: no pose in 20 of 35 (D) and 11 of 33 (E); why was not examined | docs/field-tests/2026-09-29-room-frames-results.md:62-63, 72-76 |
| One subject, one room, one lie-down per segment; near-duplicate frames; nobody fell | docs/field-tests/2026-09-29-room-frames-results.md:12-13, 93 |
| On the counter camera the walking frames show hips and legs only | docs/field-tests/2026-09-29-room-frames-results.md:81 |
| Two adversarial reviews before the run; the first found two ways a broken run could have been scored as a pass, closed before the plan was committed | docs/field-tests/2026-09-29-room-frames-results.md:100-104; docs/field-tests/2026-09-29-room-frames/reviews.md |
| Not verified at the run: container settings not inspected, network not captured | docs/field-tests/2026-09-29-room-frames-results.md:44-46 |
| D1 stays open | docs/field-tests/2026-09-29-room-frames-results.md:88-91; docs/DECISIONS.md (DR-13 status, at the merge of pull request 8) |


# Fine-tuned RF-DETR on public fall datasets: results

Results of the [pre-declared plan](2026-09-28-roboflow-finetune-plan.md) (committed `4adc303`, 2026-09-28
11:30 PDT, before any training started). Every number here is copied from the evaluation extracts in
[`2026-09-28-roboflow/`](2026-09-28-roboflow/), which hold what Roboflow's Model Evaluation returned; nothing was
recomputed. Public data only: no frame from the test room was uploaded, trained on or scored.

## 1. Answer

**F1 and F2 pass on public data.** A detector fine-tuned to predict the pose as a class separates a lying person
from a standing or sitting one on the arm-A test split: `lying` precision **1.000** and recall **1.000** at the
threshold the rule fixed (F1, bar >= 0.90 each), and **0** lying-to-upright or upright-to-lying confusions in 24
ground-truth lying instances (F2, bar <= 5 %). So a fine-tuned class split is a live option for **D1**
([DR-13](../DECISIONS.md#dr-13)) beside keypoints. What this does not show, as the plan says: whether the model
works in the test room (that needs the room-frame plan), and anything about D0.

The test split is small: 73 images, 89 instances (bed 16, lying 24, sitting 11, standing 38), one Universe
dataset of one author's rooms. The comparison arms say the same recipe reaches `fall` 0.93 / 0.98 on the URFD
frames and `lying` 0.91 / 0.95 on lying3, with 0 and 4 pose swaps respectively. Treat the pass as "the approach
is not dead on arrival", not as a recall estimate.

## 2. What ran

| Arm | Dataset (fork) | Version | Model | Training | Credits (run) |
|---|---|---|---|---|---|
| A, primary | `fall_detection-johan-jsi2o` (736 images; bed, standing, lying, sitting) | v1, 640 stretch, no offline augmentation | RF-DETR NAS (Standard), `rfdetr-nas-parent` | 18:31 to 20:30 UTC, 1 h 59 min; 37 frontier children + 4 stock baselines out of 5,011 architectures | 3.94 (NAS page, in the extract) |
| B | `fall-detection-urfd-vzgtq` (2,204; fall, not_fall) | v1, same | `rfdetr-nano` | 30 min | not recorded |
| C | `lying3-vcr6i` (5,323; standing, lying, sit), splits rebalanced 70/20/10 | v1, same | `rfdetr-nano` | 40 min | not recorded |

Deviations from the plan, all forced by tooling. Each was decided when it arose, before the verdict it could
have touched was read, and all are written down here, in the document written after the evaluations:

- **Arm B trained twice.** The first `trainings_create` call returned an internal error after it had started a
  run; the retry started a second. Same version, same recipe. The rule, fixed when the duplicate was found and
  before either evaluation was read: the run whose creation call returned successfully (`...-nano-t2`) is arm B;
  the first (`...-nano-t1`, test mAP@50 0.987 against 0.993) is reported as a seed-variance reading and not
  scored. Both are report-only arms, so no verdict depends on the choice.
- **The rule's arm-A model had no evaluation.** The platform evaluates its own `recommended` child (the fast end of
  the frontier). The plan's rule picks the child with the highest valid mAP@50-95, `...--00ba18` (96.85), so its
  evaluation was started by hand from the model page at 21:01 UTC and read when it finished. The recommended
  child is reported beside it as the device-sized candidate, which is what the plan asked for in the absence of
  size names on NAS children.
- **Confusion matrices exist at 0.1 steps only.** The rule's thresholds are 0.75 (A), 0.39 (B) and 0.44 (C); the
  matrices are read at 0.70 and 0.80 (A, identical), 0.40 (B) and 0.40 (C). Per-class precision and recall are at
  the exact thresholds.
- **NAS latency is measured on the platform's targets (AI1, T4), not on the Jetson.** F5 is the device
  measurement; it was run later the same day (section 5), after the first version of this document was committed.
- **F5 ran over the C4 manifest, not "two test frames".** The first version of section 5 described F5 as a run on
  two frames. The plan's wording is "measured the way section 5 of the RF-DETR results measured the stock models",
  which is one request per frame of the `floor-trials-1` manifest (580 frames, both cameras), and that is what ran.
  F5 has no bar, so the wording changed nothing scored; section 5 was rewritten with the numbers.

## 3. Arm A, scored

Model `...-rfdetr-nas-t1--00ba18`. Two valid-split mAP@50-95 figures exist for it and both are quoted with
their source: **96.85** is the NAS run's own per-child metric (`trainings_get`, the NAS page), the number the
selection rule was applied to because no Model Evaluation existed at selection time; **0.963** is what Model
Evaluation reported afterwards for the same model and split. They are two evaluators, not one number rounded
twice; the results below use Model Evaluation throughout. Test mAP@50 **0.974**, test mAP@50-95 **0.952**
(per class, test: bed 1.000 / 0.971, lying **1.000 / 0.950**, sitting 0.928 / 0.928, standing 0.967 / 0.958).
Valid-optimal threshold **0.75** (valid: precision 0.972, recall 0.971), applied to test.

| Test split at 0.75 | Precision | Recall | F1 |
|---|---|---|---|
| overall | 0.933 | 0.967 | 0.944 |
| bed | 1.000 | 1.000 | 1.000 |
| **lying** | **1.000** | **1.000** | 1.000 |
| sitting | 0.733 | 1.000 | 0.846 |
| standing | 1.000 | 0.868 | 0.930 |

Confusion matrix, test split, read at 0.70 and at 0.80 (the two are identical; rows: ground truth, columns:
predicted):

| | bed | lying | sitting | standing | missed |
|---|---|---|---|---|---|
| **bed** (16) | 16 | 0 | 0 | 0 | 0 |
| **lying** (24) | 0 | **24** | 0 | 0 | 0 |
| **sitting** (11) | 0 | 0 | 11 | 0 | 0 |
| **standing** (38) | 0 | 0 | 4 | 33 | 1 |
| **false positives** | 0 | 0 | 0 | 0 | |

| Condition | Bar | Measured | Verdict |
|---|---|---|---|
| **F1** lying separable | precision >= 0.90 and recall >= 0.90 | 1.000 / 1.000 | **PASS** |
| **F2** lying not confused with upright | <= 5 % of 24 lying instances | 0 of 24 (0 %) | **PASS** |
| **F3** bed (report only) | none | bed as lying 0, lying as bed 0 | reported |
| **F5** device fit (report only) | none | `e65db0` 78.7 ms, `00ba18` 125.2 ms serial round trip on the Jetson; floor 2,799 MB with both resident (section 5) | reported |

The model's errors are all on the upright side: 4 standing instances read as sitting and 1 missed. The platform's
own recommendations for this evaluation say the same (missed standing 2, standing confused with sitting 3, at its
0.85 threshold) and flag class imbalance: sitting has 11 test instances. `lying` is 1.000 / 1.000 on the test
split at every threshold from 0.11 to 0.87 in the committed
[per-threshold sweep](2026-09-28-roboflow/arm-A-00ba18-sweep.json), so F1 does not hinge on the 0.75.

**Device-sized candidate.** The platform's `recommended` child, `...--e65db0`, is the fast end of the frontier
(2.93 ms on AI1, 1.16 ms on T4, against 18.2 / 4.66 ms for `00ba18`) at a lower box accuracy: test mAP@50 0.971,
mAP@50-95 0.841, `lying` 1.000 / 0.866. At each class's own optimal threshold on test it reads lying 1.000 /
1.000, sitting 0.786 / 1.000, standing 1.000 / 0.947 (report only; not the plan's threshold rule, not scored). The
four stock RF-DETR baselines trained inside the same run scored valid mAP@50-95 93.3 to 96.0 at 7.6 to 25.1 ms on
AI1; the search's gain over them is in latency (82.9 % by the platform's figure), not accuracy.

## 4. Arms B and C, report only (F4)

Both trained `rfdetr-nano` from the COCO checkpoint with default hyperparameters. Threshold rule as declared.

| Arm | Model | Test mAP@50 | Test mAP@50-95 | Valid-optimal threshold | Test at that threshold, overall P / R / F1 | Down class on test, P / R |
|---|---|---|---|---|---|---|
| B, URFD | `fall-detection-urfd-vzgtq-1-rfdetr-nano-t2` | 0.993 | 0.901 | 0.39 | 0.952 / 0.986 / 0.969 | `fall` 0.931 / 0.982 |
| C, lying3 | `lying3-vcr6i-1-rfdetr-nano-t1` | 0.926 | 0.658 | 0.44 | 0.837 / 0.933 / 0.882 | `lying` 0.910 / 0.950 |

| B, URFD, test at 0.40 | fall | not_fall | missed |
|---|---|---|---|
| **fall** (110) | 108 | 0 | 2 |
| **not_fall** (109) | 0 | 108 | 1 |
| **false positives** | 8 | 3 | |

| C, lying3, test at 0.40 | lying | sit | standing | missed |
|---|---|---|---|---|
| **lying** (299) | 286 | 2 | 0 | 11 |
| **sit** (176) | 2 | 163 | 0 | 11 |
| **standing** (305) | 0 | 0 | 295 | 10 |
| **false positives** | 30 | 54 | 63 | |

Read the way F2 reads arm A (not scored): arm B swaps `fall` and `not_fall` **0** times in 110; arm C swaps
`lying` with an upright pose **4** times in 299 (1.3 %). Arm C's errors are misses (11 of 299 lying) and false
positives on background, and its weakest class is `sit` (precision 0.771), which is the pose behind the 09-26
false WARN on the LIDAR side. The gap between arm A and arm C is not scored; it says that the harder, larger
dataset with a nano model lands around 0.91 / 0.95 on the down class. No bar applies to arms B and C.

## 5. F5, device fit (report only)

Run on the Jetson at 22:54 to 22:58 UTC, the way [section 5 of the stock RF-DETR results](2026-09-27-rfdetr-results.md#5-cost-on-the-device-c4-report-only)
measured the stock models: one request per frame of the `floor-trials-1` manifest (580 frames, both cameras,
1280x720 JPEG), serially, one in flight, to `http://127.0.0.1:9001` and nowhere else; the first call timed on its
own, then 3 untimed warm-ups; `MemAvailable` and jtop GPU % sampled every 0.5 s. Runner:
[`jetson/f5_device_fit.py`](../../jetson/f5_device_fit.py) (in the repo, with a
[test](../../src/prevera_perception/test/test_f5_device_fit.py) against a stub server that reads what it sends).
Raw output, without frames or predictions: [`f5-e65db0.json`](2026-09-28-roboflow/f5-e65db0.json),
[`f5-00ba18.json`](2026-09-28-roboflow/f5-00ba18.json), [`f5-smoke-e65db0.json`](2026-09-28-roboflow/f5-smoke-e65db0.json)
(the 5-frame smoke test that pulled `e65db0`), [`f5-00ba18.log`](2026-09-28-roboflow/f5-00ba18.log).

| Model | Input | Client latency median / p90 (ms) | Server processing median (ms) | Serial fps | `first_call_s` | `MemAvailable` before run → min (MB) | GPU max % (0.5 s samples) | `/scan` msgs per ~5 s, before → after |
|---|---|---|---|---|---|---|---|---|
| `...--e65db0`, recommended child, confidence 0.56 | 288x288 | **78.7 / 82.4** | 59.7 | 12.7 | 17.5 (smoke run: pull + load, cold cache); 0.1 once resident | 5214 → 3675 (smoke run, the load); 3705 → 3655 (full run) | 98.6 | 47 → 47 |
| `...--00ba18`, the rule's pick, confidence 0.75 | 640x640 | **125.2 / 132.1** | 107.7 | 8.0 | 9.1 (pull + load, `e65db0` resident) | 3703 → 2799 (both resident) | 99.6 | 29 → 46 |
| rfdetr-nano, stock, 2026-09-27 | not read | 107.9 / 114.6 | 88.4 | 9.3 | 2.4 (cached) | 3109 → 2866 | 99.3 | 39 → 43 |
| rfdetr-base, stock, 2026-09-27 | 560x560 | 126.9 / 131.2 | 109.1 | 7.9 | 1.8 (cached) | 2916 → 2910 | 99.6 | 47 → 46 |
| rfdetr-medium, stock, 2026-09-27 | 576x576 | 126.9 / 132.7 | 109.1 | 7.9 | 1.3 (cached) | 2992 → 2584 | 99.5 | not relayed |

What it says, in the same terms as the 09-27 columns:

- **The rule's pick costs what stock base and medium cost.** `00ba18` at 640x640 is 125.2 ms per frame, 107.7 ms
  of it in the server; base and medium were 126.9 and 109.1. The recommended child is **27 % faster than stock
  nano** (78.7 against 107.9 ms) at a 288x288 input. Client minus server is 19.0 and 17.5 ms, the same 18 to
  19 ms of HTTP and JSON as on 09-27: the fixed cost of a 1280x720 JPEG round trip does not shrink with the model.
- **The Jetson gap between the two children is 1.6x (client) to 1.8x (server), not the 4x (T4) or 6x (AI1)
  the platform's latency targets show.** At these sizes the fixed decode, resize and transport cost dominates
  on the Orin Nano. The platform's targets rank the children; they do not predict the device.
- **Memory.** Loading `e65db0` into a fresh container took `MemAvailable` from 5214 to 3675 MB; the floor with both
  children resident (`MAX_ACTIVE_MODELS=2`) is **2,799 MB**, next to the 2,584 MB floor of 09-27 with two stock
  models. As on 09-27, only the minimum is usable; the server's own `vram_bytes` (605 MB for `e65db0`, 352 MB for
  `00ba18`) is not consistent with it and is not used. Cameras were off, so the capture load of a production
  setup is absent from every number here.
- **`/scan`.** 47 before and after `e65db0`. The 29 before `00ba18` is a single reading taken between the runs,
  with no request in flight, thirty seconds after a 47; it is measurement jitter of the same kind as nano's 39 on
  09-27, and 46 after the run. What happens *during* a run was measured later the same evening; see "Co-load"
  below.
- **`first_call_s` is a cold pull for `e65db0`** (17.5 s: the container had just been started and the model was
  not in `/opt/nvme/inference-cache`), and pull plus load for `00ba18` (9.1 s). Those are the numbers a restart
  pays; on 09-27 the weights were already cached.
- **The model ran on every frame** (580 of 580 answered, 0 errors, for both; 514 and 501 frames returned at least
  one box). That count is the only trace of the predictions: the runner discards them by design, because reading
  what a fine-tuned model detects in room frames is a room result, and a room result needs its plan declared
  first ([PROCESS](../PROCESS.md)). Nothing in this section is one.

Conditions, recorded here because the 09-27 document could not read them: container started at about 22:50 UTC
with the DR-11 hardened command, verified by `docker inspect` (`ReadonlyRootfs=true`, port binding
`127.0.0.1:9001` only, `TRITON_CACHE_DIR=/tmp/triton-cache`, `MAX_ACTIVE_MODELS=2`, `ACTIVE_LEARNING_ENABLED=False`,
`TELEMETRY_OPT_OUT=True`, key from `--env-file ~/.roboflow.env`, `--cap-drop=ALL --cap-add=NET_BIND_SERVICE`,
`--security-opt=no-new-privileges`); every request carried `disable_active_learning: true` (the runner's test
checks this); the LIDAR driver and fall detector were restarted at 22:51 UTC after a reboot had left the driver up
with 0 scans, and read 44 to 47 scans per 5 s before the runs; no camera capture process was running; the
Jetson's ROS checkout was `fix/background-absorption @ 7b705c2`, not `main`. Egress was captured later the same
evening ("Egress" below): the server posts more than the model pull.

**Co-load (CL1, CL2; bars fixed in [the close-the-gaps plan](../plans/2026-09-28-close-the-gaps-plan.md), committed
at 23:25 UTC, before the bags at 23:32).** Two 60-second bags of `/scan` and `/fall_events` (`ros2 bag record -s
mcap`), LIDAR stack up, cameras off, container up with `e65db0` resident: one idle, one with the 580-frame
`e65db0` run inside it from second 5 to second 53. Read with
[`scan_rate.py`](../../tools/bag_analysis/scan_rate.py) from header stamps ([idle](2026-09-28-roboflow/coload-idle.json),
[load](2026-09-28-roboflow/coload-e65db0.json); the runner's own figures for that run are in
[`f5-coload-e65db0.json`](2026-09-28-roboflow/f5-coload-e65db0.json)):

| Bag | `/scan` msgs | Span (s) | Rate (Hz) | Largest gap (s) | Gaps > 0.5 s | `/fall_events` |
|---|---|---|---|---|---|---|
| idle | 567 | 56.5 | 10.009 | 0.104 | 0 | 0 |
| `e65db0` serving inside | 594 | 59.2 | 10.009 | 0.105 | 0 | 0 |

- **CL1, count within ±10 % of idle: 594 against 567, +4.8 %, PASS.** The counts differ by the recorders' spans
  (the first recorder took longer to subscribe); the rates are identical to three decimals.
- **CL2, no gap over 0.5 s: 0 in both, PASS.** The largest gap under load is 0.105 s, one scan period plus a
  millisecond, the same as idle.
- Report only: the runner inside the recording measured 77.4 / 81.2 ms (median / p90), server 58.8 ms, 12.9 fps,
  against 78.7 / 82.4 earlier: recording the bag cost the camera path nothing visible. `MemAvailable` 2601 → 2517 MB
  with both children still resident and the recorder running. `/fall_events` stayed silent in both bags; nobody was
  asked to be in the room and nothing is claimed about the detector's behaviour under load beyond that.

So on this evening's evidence the camera path does not disturb the LIDAR path: the scan stream ran at 10.009 Hz
with no dropout while the GPU served 580 frames in 48.1 s (12.9 serial fps by the median, 12.1 frames per
second wall clock). That is one run of one child on one Jetson with the
cameras off; the claim in DR-11 is updated to that extent and no further.

**Egress (EG1, EG2; bars fixed in the same plan, committed before the capture).** Jeremy ran `tcpdump -i any -n
'not port 22 and not host 127.0.0.1'` on the Jetson (`sudo`, his) from about 23:40 to 23:42 UTC; inside it the agent
ran the 580-frame `e65db0` pass once more (23:40:39 UTC, 47.4 s, 77.6 ms median, model already resident, so no pull
happened in this capture). The text dump is scored by [`egress_summary.py`](../../tools/jetson/egress_summary.py)
over the Jetson's two addresses (wired `.60` on the default route, Wi-Fi `.39`); the container's own leg on
`docker0` and its veth is counted separately as the positive control ([extract](2026-09-28-roboflow/egress-e65db0.json)
with every command; [runner figures](2026-09-28-roboflow/f5-egress-e65db0.json); the pcap stays on the Jetson at
`/opt/nvme/reports/egress-e65db0.pcap`).

| Window | Bytes out, non-LAN | Bytes in, non-LAN | Destinations | Container leg (frames in) | Other non-LAN |
|---|---|---|---|---|---|
| the 580-frame loop (47.4 s) | **285,098** | 37,682 | `151.101.65.195:443` only | 82.3 MB | 0 |
| whole run (first call to last response) | 285,098 | 37,682 | same | 82.3 MB | 0 |
| whole capture (about 2 min) | 295,120 | 75,614 | `151.101.65.195:443`, `151.101.1.195:443` | 82.4 MB | 0 |

- **The LAN definition.** The plan wrote the bar with `192.168.4.0/24`; the room's network is a `/22`
  (`192.168.4.0/22`, both Jetson addresses in it), and the parser committed at 23:37 UTC, before the capture, uses the
  four `/22` prefixes. The change is disclosed here rather than hidden in the tool: under `/24` the EG1 figure is the
  same 285,098 bytes, and the only difference is 2,996 bytes of broadcast chatter between other LAN hosts
  (`192.168.5-7.x`) that the `/24` reading files under "other", none of it from the Jetson. Verdicts are unchanged
  either way.
- **EG1, under 200,000 bytes outbound during the loop: 285,098, FAIL.** The bar stands as declared. The bytes are
  one post of **280,086 bytes at 23:41:23 UTC** (44 s into the loop, 3 s before its end) plus three exchanges of
  about 2.4 KB at 23:41:13, 23:41:22 and 23:41:44. The 580 frames went to the container over the docker bridge in
  the same window, 82.3 MB of them (the positive control: the capture saw them); 0.3 % of that came out, as one
  burst, not as 580 pieces, so **frames did not leave**. What did: by the Inference 1.7.2 source, the
  **model-monitoring pingback**, not the usage collector. `METRICS_ENABLED` defaults to True, `METRICS_INTERVAL`
  to 60 s and `METRICS_URL` to `{API_BASE_URL}/inference-stats` (`inference/core/env.py:759-767`);
  `PingbackInfo.post_data` (`inference/core/managers/pingback.py`) posts, once per interval, every inference the
  server cached in the last 60 s, and the cache holds one record per request (`managers/base.py:342-367`). With the
  default `TINY_CACHE` a record is the request's `api_key` (in clear), `confidence`, `model_id`, `model_type`,
  `source`, `source_info`, the inference id and server id, and the response condensed to one `{class, confidence}`
  per detection (`inference/core/cache/serializers.py:33-46, 104-107`); images are stripped, boxes are not included.
  Each post also carries the container's hostname, IP and MAC (`managers/metrics.py:80-83`). About 550 requests fell
  in that 60 s window at roughly 510 bytes each: 280 KB. The three small exchanges every ~10 s fit the usage
  collector, which aggregates per model and posts to `api.roboflow.com/usage/inference` every `flush_interval`
  of 10 s (`inference/usage_tracking/config.py`); it is a separate channel with its own endpoint. **The capture
  cannot read TLS**: the attribution rests on the size, the 60 s cadence, the 8 DNS lookups and 8 TCP connections
  to `api.roboflow.com` in the capture, and the code; a re-capture with `METRICS_ENABLED=False` is the test that
  would confirm it (handoff, next item 1).
- **Correction (2026-09-29), written beside EG1, not over it.** The re-capture below showed that this capture began
  late: its first packet is at 23:41:13.05 UTC, 34.4 s after the runner's first request (23:40:38.62 UTC), so it
  holds the last 13.4 s of the 47.4 s loop, 167 of the 580 frames (167 SYNs to port 9001 on `docker0`; 40.7 MB of
  frame payload against 166.2 MB for the full set, which is 124.7 MB of JPEG in base64). The extract's "about
  23:40:00 to 23:42" was wrong. What changes: 285,098 bytes is a lower bound over 28 % of the loop plus the one
  pingback post, so the FAIL stands; "82.3 MB of them (the positive control: the capture saw them)" was true of 167
  frames, not of the loop. The [extract](2026-09-28-roboflow/egress-e65db0.json) carries the same correction under
  `capture_correction_2026-09-29`, its original lines untouched.
- **EG2, every non-LAN destination is a Roboflow host: PASS.** Both addresses seen are the capture's own DNS answers
  for `api.roboflow.com` (8 A queries, seen on three interfaces each with `-i any`, and `api.roboflow.com` as the
  TLS server name). The operating system's `connectivity-check.ubuntu.com` lookups carried no bytes in any window.
  Nothing left over IPv6 (the Jetson's four global-scope addresses are `fd0c::/16` ULA; "other non-LAN" is 0).
  The 69 unparsed lines are 40 ARP and 29 `ifindex` frames, none of them IP.
- **What EG1 found is that the privacy configuration of 09-27 does not do what it says.** `TELEMETRY_OPT_OUT=True`
  is inert in 1.7.2: `TelemetrySettings` has no opt-out field (`inference/usage_tracking/config.py`). The pingback
  was never addressed at all: nothing in the DR-11 command sets `METRICS_ENABLED`. So during every run of 09-27 and
  09-28 the server posted, once a minute, a timestamped record of every request with the class and confidence of
  every detection, the API key in clear, and the device's hostname, IP and MAC. Not frames, not boxes; but for a
  detector in a resident's room, "lying, 0.97, 23:41:05" is a fact about the room, and it left. **Mitigations, none
  applied tonight** (each changes what the server does and gets its own pre-declared re-capture): `METRICS_ENABLED=False`
  in the container environment (stops the pingback; `pingback.py:82-86` logs that it is disabled), or
  `disable_model_monitoring: true` in every request (per-request opt-out, `entities/requests/inference.py:41`);
  for the usage channel, `METRICS_COLLECTOR_BASE_URL` pointed at a local sink; `OFFLINE_MODE=True` disables both
  but `env.py` warns it leaves authentication and usage accounting undefined and a workspace model may then refuse
  to load. **Recorded in DR-11 as the open privacy item, and whether per-request metadata leaving is acceptable at all
  is Jeremy's decision, not a setting.**
- Not verified: a capture during a model pull (the weights download, and whatever accompanies it). This capture had
  the model resident.

**Egress, re-capture with `METRICS_ENABLED=False` (2026-09-29; [plan](2026-09-28-egress-recapture-plan.md) committed
at 00:37 UTC, bars and windows unchanged from EG1/EG2).** Jeremy restarted the container with
[`jetson/inference-server-up.sh`](../../jetson/inference-server-up.sh) (the DR-11 command with that one flag added;
`docker inspect` showed `readonly=true`, `127.0.0.1:9001`, `ACTIVE_LEARNING_ENABLED=False`, `TELEMETRY_OPT_OUT=True`,
`METRICS_ENABLED=False`, `TRITON_CACHE_DIR`, `MAX_ACTIVE_MODELS=2`), started the same `tcpdump` at 00:57:28 UTC, and
the agent ran the same 580-frame `e65db0` pass at 01:09:21 UTC (47.5 s, 77.4 ms median, 0 errors; only `e65db0`
resident this time, 4.5 GB free). The capture ran until 01:31:44 UTC: 11.9 minutes before the run and 21.6 after it,
so a 60 s pingback interval would have fired at least twenty times inside it. Same scorer, same `/22` prefixes
([extract](2026-09-28-roboflow/egress-recapture-e65db0.json) with the per-second profile, DNS and connection counts
and every command; [runner figures](2026-09-28-roboflow/f5-egress-recapture-e65db0.json); pcap on the Jetson at
`/opt/nvme/reports/egress-recapture-e65db0.pcap`, 353 MB).

| Window | Bytes out, non-LAN | Bytes in, non-LAN | Destinations | Container leg (frames in) | Other non-LAN |
|---|---|---|---|---|---|
| the 580-frame loop (47.5 s) | **12,987** | 56,495 | `151.101.65.195:443`, `151.101.1.195:443` | 333.7 MB | 0 |
| whole run (first call to last response) | 12,987 | 56,495 | same | 336.7 MB | 0 |
| after the run (21.6 min) | 3,305 | 10,038 | `151.101.65.195:443` once, then `connectivity-check.ubuntu.com` | 1.7 MB (DDS multicast, see below) | link-scope only |
| whole capture (34.3 min) | 20,101 | 108,549 | the two above, `api.github.com`, Ubuntu connectivity checks, one NTP | 338.8 MB | link-scope only |

- **EG1, under 200,000 bytes outbound during the loop: 12,987, PASS.** Six connections to `api.roboflow.com`, at
  01:09:23 (two), :34, :44, :54 and 01:10:05, of 804 to 2,437 bytes each, then one more of 2,435 bytes at 01:10:15
  after the last request, and nothing to Roboflow for the remaining 21.5 minutes. The pingback posts every 60 s
  whether or not there were requests (`pingback.py`, `post_data`), so about 34 posts were due in this capture had
  the flag not taken; the seven usage flushes are the only connections to Roboflow in it. `usage.db`'s mtime is that
  last flush (01:10:15; `usage` table still 0 rows).
- **EG2, every non-LAN destination is a Roboflow host: PASS.** Both addresses are the capture's own DNS answers for
  `api.roboflow.com` (7 A queries on each of three interfaces, answers matched to queries by transaction id; the AAAA
  answer `2620:0:890::100` was never used). Nothing else received a byte in the loop or the run.
- **Predictions, one by one.** (1) *The 280 KB post does not recur*: confirmed; the largest second of egress in 34
  minutes is 3,240 bytes, so the pingback attribution stands and `METRICS_ENABLED=False` is what turns it off.
  (2) *Under 20,000 bytes in the loop, all usage-collector exchanges*: confirmed, 12,987 bytes in ~2.4 KB exchanges
  every ~10 s. (3) *Model resident, first call under a second, no pull*: half right. No pull (56 KB came in during
  the loop, nothing model-sized), but the first call took 1.8 s, not 0.1 s: the container was fresh and loaded the
  weights from the cache volume. The pull gap stays open. (4) *Container leg about 82 MB as before*: wrong, and
  informative: 333.7 MB, which is 2 × 166.2 MB in (the 124.7 MB of JPEG as base64, seen on `docker0` and the veth)
  plus 2 × 0.5 MB of responses. That is the whole set, and it exposed the coverage gap in the 23:41 capture recorded
  above under EG1. The bucket also holds 1.4 KB/s of `172.17.0.1 > 239.255.0.1:17900`, ROS 2 DDS discovery for
  domain 42 (7400 + 250 × 42) that the LIDAR stack multicasts on every interface, the docker bridge included:
  multicast, not egress, and the exposure [ARCHITECTURE, section 7](../ARCHITECTURE.md#7-ports-and-exposure) already lists.
- **What still leaves, by the code** (TLS keeps the bytes unread; the sizes are the capture's, the fields are
  `inference/usage_tracking/collector.py` `empty_usage_dict`, `system_info`, `_offload_to_api` and
  `payload_helpers.py` `send_usage_payload` in 1.7.2): every ~10 s while requests arrive, one POST to
  `api.roboflow.com/usage/inference` carrying, per API key, the **key in clear** (in the JSON body and as a Bearer
  header), the sha256 of the hostname and of the IP, an execution session id, the model id, `processed_frames`, fps,
  source duration, megapixel buckets, execution duration, Python and Inference versions and an enterprise flag.
  Aggregated: no per-detection field, no class, no confidence, no image. `TelemetrySettings` (`env_prefix`
  `telemetry_`) has no off switch; `TELEMETRY_API_USAGE_ENDPOINT_URL` or `METRICS_COLLECTOR_BASE_URL` can point it at
  a local sink, `OFFLINE_MODE=True` stops it with the caveats recorded under EG1.
- **A third channel, found outside the loop.** Four connections to `api.github.com` (`140.82.116.5`, the capture's
  DNS answer), 788 bytes out each, two per container start (01:06:35 and 01:07:17 for the first container, 01:07:34
  and 01:08:13 for the running one), from the container's address: the **version check**, `GET
  https://api.github.com/repos/roboflow/inference/releases/latest` at import of `inference.core`
  (`inference/core/__init__.py`, `get_latest_release_version`; `VERSION_CHECK_MODE` defaults to `once`). No key and
  no data in it, but a request to a third party from the inference container at every start, which
  `DISABLE_VERSION_CHECK=True` turns off (`env.py`; `OFFLINE_MODE` and `SECURE_GATEWAY` imply it). It was not set in
  the script as run tonight; the flag is added to `inference-server-up.sh` after this capture and is **not yet
  verified by a capture**.
- **The rest of the 20,101 bytes** is the host operating system, none of it Inference: one 87-byte
  `connectivity-check.ubuntu.com` request per interface every 5 minutes (NetworkManager, 1,479 bytes in all), one NTP
  exchange (48 bytes) and one bare SYN to `1.1.1.1:80`. The "other" bucket outside the run windows is IPv6 neighbour
  solicitations from `::` and DHCP discovers from `0.0.0.0`: link-scope frames with no source address, which any host
  on the link can have sent; the scorer counts them because it cannot place them, and none fall in a run window.
- **What is verified for DR-11 after this run:** with `METRICS_ENABLED=False` the per-request record (class,
  confidence, key, hostname, IP, MAC) no longer leaves; what leaves during inference is the usage collector's
  aggregated ~2.4 KB every ~10 s with the API key in clear, and at container start the version check to GitHub.
  Frames did not leave (the full 166 MB went to the container, 13 KB came out). One run, one child, cameras off, no
  pull captured.

**For D0** the round trip to carry forward is **79 ms** (`e65db0`) or **125 ms** (`00ba18`) per frame, serial, one
camera, cameras off, with about 2.8 GB of headroom with both resident, replacing the stock models' 108 to 127 ms.

## 6. What this changes

- **D1** ([DR-13](../DECISIONS.md#dr-13)) now has one measured "no" (box shape, C3), one unscored run (the v1
  keypoint run, invalid under its own rule, awaiting the [v2 rescore](2026-09-28-rfdetr-keypoints-plan-v2.md)) and
  one measured "yes on public data" (this plan). The room-frame measurement is the next step for the class split;
  which of the two runs first is Jeremy's call.
- **D0** ([DR-14](../DECISIONS.md#dr-14)) gets its camera half as a runnable artefact: the
  [time-on-floor Workflow](../../tools/roboflow/README.md) takes any of these models by id and returns seconds since
  a down-pose track entered a floor polygon, the unit the LIDAR detector's stillness clock uses. Its clock is
  specified and validated structurally; it has not been run on video.
- **The bed.** `bed` labels the furniture, and the model never confused it with a lying person on 16 + 24
  instances. A person lying **in** the bed is a different question that this label set cannot ask; the Workflow's
  floor polygon is the mechanism that keeps in-bed lying out of the count until a dataset asks it.

## 7. What is not known

- **Whether train and test share near-duplicate frames.** The three datasets are video-derived and their splits
  are the uploaders'; nothing here checked for frames of the same sequence on both sides of the split, which is
  the most likely way a 24-of-24 could be inflated. Until that is checked, the arm-A numbers are an upper bound.
- **One run per arm.** Arm A was trained once; its seed variance is unmeasured (arm B's accidental duplicate moved
  test mAP@50 by 0.006). One dataset, 73 test images, 89 instances, 11 of them sitting.
- **Two evaluators.** The selection rule ran on the NAS run's own valid metric; the scoring ran on Model
  Evaluation. Whether the rule would have picked the same child under Model Evaluation's numbers is not known,
  because only two children were evaluated.
- **Thresholds.** Per-class precision and recall are at the rule's exact thresholds; the confusion matrices are at
  the nearest stored 0.1 step. For arm A the two neighbours (0.70, 0.80) agree, which bounds F2; for arms B and
  C the matrix at 0.40 stands in for 0.39 and 0.44.
- **The device-sized candidate is not scored** under the plan's rule; its per-class numbers are at each class's
  own optimal threshold, as the platform reports them.
- **F5 is serial, one camera, cameras off.** The Jetson figures in section 5 are one request in flight at a time
  with no capture running. Co-load was measured once (CL1, CL2 in section 5): the scan stream held 10 Hz with no
  dropout during one `e65db0` run; the detector's behaviour under load beyond a silent `/fall_events` is not
  claimed. Egress was captured for two runs (section 5): the first (EG1 FAIL, EG2 PASS, and it began 34 s late)
  showed the model-monitoring pingback (one record per request, class and confidence per detection, key in
  clear) leaving once a minute under the DR-11 command as written; the re-capture with `METRICS_ENABLED=False`
  (EG1 PASS at 12,987 bytes, EG2 PASS) confirmed that flag stops it and left the usage collector's aggregated
  ~2.4 KB every ~10 s (API key in clear, hashed hostname and IP, counts) and a version check to GitHub at container
  start. TLS keeps the content unread; the fields are the code's. No capture covered a model pull. The NAS
  latencies elsewhere in this document are the platform's AI1 and T4 targets, which section 5 shows do not predict
  the device.
- **Licences and provenance** are as the Universe uploaders state them; the URFD copy's CC BY 4.0 was not checked
  against the original dataset's terms.
- **Nothing here is a room result.** No frame from the test room was involved, by design.

## Reproduce

F5, on the Jetson, with the container up under the DR-11 command (section 5 lists the verified environment) and
the LIDAR stack running (`~/guardian-status.sh` shows driver 1, detector 1, about 50 scans per 5 s):

```bash
set -a; . ~/.roboflow.env; set +a          # ROBOFLOW_API_KEY into the environment, never on a command line
python3 jetson/f5_device_fit.py jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--e65db0 --confidence 0.56
python3 jetson/f5_device_fit.py jeremy-gracey/fall_detection-johan-jsi2o-1-rfdetr-nas-t1--00ba18 --confidence 0.75
```

Forks, versions, training ids, model ids and evaluation ids are in the three extracts. Training and evaluation
ran on Roboflow on 2026-09-28; the NAS run is at
`app.roboflow.com/jeremy-gracey/fall_detection-johan-jsi2o/nas-runs/1`, the evaluations at
`.../fall_detection-johan-jsi2o/evaluation/1`, `.../fall-detection-urfd-vzgtq/evaluation/1` and
`.../lying3-vcr6i/evaluation/1` (workspace login). Trained models are under Roboflow's Platform Model License
(PML-1.0, as shown on the run); the datasets are CC BY 4.0 by their Universe authors:

```
@misc{fall_detection-johan_dataset, title={Fall_Detection Dataset}, author={FYP}, year={2026}, publisher={Roboflow},
  howpublished={\url{https://universe.roboflow.com/fyp-isiva/fall_detection-johan}}}
@misc{fall-detection-urfd_dataset, title={Fall detection URFD Dataset}, author={Me}, year={2026}, publisher={Roboflow},
  howpublished={\url{https://universe.roboflow.com/me-15gfc/fall-detection-urfd}}}
@misc{lying3_dataset, title={lying3 Dataset}, author={poscoproject}, year={2022}, publisher={Roboflow},
  howpublished={\url{https://universe.roboflow.com/poscoproject/lying3}}}
```

The URFD frames derive from the UR Fall Detection Dataset (Kwolek and Kepski, 2014); the Universe copy carries a
CC BY 4.0 label from its uploader, which this repository relays without verifying against the original terms.

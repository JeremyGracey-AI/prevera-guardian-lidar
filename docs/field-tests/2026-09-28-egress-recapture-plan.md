# Egress re-capture with `METRICS_ENABLED=False`: pre-declared plan

Committed before the run (DR-17). Follows the failed EG1 of [the close-the-gaps plan](../plans/2026-09-28-close-the-gaps-plan.md),
Task 6, and its record in [the fine-tune results, section 5](2026-09-28-roboflow-finetune-results.md).

## Question

Does `METRICS_ENABLED=False` stop the 280 KB post to `api.roboflow.com` that a full 580-frame run produced at 23:41:23
UTC, and what, if anything, still leaves?

## What changes, and nothing else

- The container is restarted with [`jetson/inference-server-up.sh`](../../jetson/inference-server-up.sh): the DR-11
  hardened command with one added line, `-e METRICS_ENABLED=False`. Same image (`roboflow-inference-server-jetson-6.2.0:latest`,
  Inference 1.7.2), same cache volume, same key file.
- Same capture (`tcpdump -i any -n 'not port 22 and not host 127.0.0.1'`, Jeremy's `sudo`), same runner
  (`f5_device_fit.py ...--e65db0 --confidence 0.56`, 580 frames), same scorer
  (`tools/jetson/egress_summary.py`, `/22` prefixes, both Jetson addresses), same windows.
- The LIDAR stack is restarted first with the new `guardian-up.sh` (bridges on loopback); that is a device-state
  fix, not part of the measurement.

## Bars, unchanged from Task 6

- **EG1:** bytes out to non-LAN addresses during the 580-frame loop under 200,000. PASS / FAIL.
- **EG2:** every non-LAN destination that received bytes resolves to a Roboflow host (or NTP/DNS). PASS / FAIL.

## Predictions, written before the run

1. **The 280 KB post does not recur.** If it does, the pingback attribution in results section 5 is wrong and the
   record says so beside the numbers.
2. **Under 20,000 bytes leave during the loop**, all of it the usage collector's ~2.4 KB exchanges every ~10 s to
   `api.roboflow.com` (the channel `METRICS_ENABLED` does not touch). EG1 PASS, EG2 PASS.
3. The model is resident (first call under a second), so no pull is captured; that gap stays open as before.
4. The container leg carries about 82 MB of frames in the loop window, as before (positive control).

## What gets written

- `docs/field-tests/2026-09-28-roboflow/egress-recapture-e65db0.json`: the scorer's three windows, the per-second
  profile to any non-LAN address, the DNS and connection counts by interface, the commands.
- Results section 5: an "Egress, re-capture" paragraph beside the failed EG1, verdicts and predictions checked
  one by one. The failed EG1 stays as written.
- DR-11: status updated to what is verified after this run.
- The handoff's next item 1 rewritten to what remains.

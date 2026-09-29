# Container-start capture with `YOLO_OFFLINE=True`: pre-declared plan

Committed before the run (DR-17). The third start-time probe found by capture on 2026-09-29
([results, section 5, "Container start"](2026-09-28-roboflow-finetune-results.md)) gets the same treatment as the
first two: one flag, one capture, the [same bars](2026-09-29-version-check-capture-plan.md).

## Question

With `YOLO_OFFLINE=True` added to the command ([`jetson/inference-server-up.sh`](../../jetson/inference-server-up.sh)
at `c332945`), does anything at all leave the container between `docker run` and its first request?

## What changes, and nothing else

- The script on the Jetson is replaced by the repo's `c332945` version (one added line, `-e YOLO_OFFLINE=True`, and
  that name in the inspect grep). Same image, cache volume, key file.
- Same procedure as the version-check capture: Jeremy's `tcpdump -i any -n 'not port 22 and not host 127.0.0.1'`
  first, then `sudo ~/inference-server-up.sh`, no request sent, Ctrl-C at least 120 s after `/info` answers.
- Same scorer, whole capture, container attribution by `172.17.0.2` as source on `docker0`.

## Bars, unchanged

- **VC1:** zero DNS queries for `api.github.com` and zero TCP connections from `172.17.0.2` to any non-LAN address
  in the whole capture. PASS / FAIL.
- **VC2:** `/info` answers within 120 s of `docker run`, and the inspect line prints `YOLO_OFFLINE=True` beside the
  other flags. PASS / FAIL.

## Predictions, written before the run

1. VC1 PASS with 0 connections: the two probes seen so far at start were the version check (off, verified) and
   ultralytics' online check (this flag). Nothing else in the 1.7.2 code path runs at import with a socket.
2. VC2 PASS, `/info` at about 100 s.
3. The only non-LAN traffic is the host's connectivity checks (87 bytes each, every 5 minutes per interface).
4. Nothing model-sized comes in.

## What gets written

- `docs/field-tests/2026-09-28-roboflow/yolo-offline-capture.json`: the scorer's window, the container-sourced lines,
  DNS names, the `/info` time, the inspect line, the commands.
- Results section 5, one paragraph after "Container start": VC1, VC2, predictions checked one by one.
- DR-11 and the handoff's item 1(b): what is verified after this run.

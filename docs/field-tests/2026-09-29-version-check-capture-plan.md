# Container-start capture with `DISABLE_VERSION_CHECK=True`: pre-declared plan

Committed before the run (DR-17). Follows the [egress re-capture](2026-09-28-egress-recapture-plan.md), whose capture
found the container reaching `api.github.com` twice per start ([results, section 5, "Egress, re-capture"](2026-09-28-roboflow-finetune-results.md)),
and Jeremy's decision of 2026-09-29 that the usage collector's aggregated record may leave, for now (DR-11).

## Question

With `DISABLE_VERSION_CHECK=True` on the command ([`jetson/inference-server-up.sh`](../../jetson/inference-server-up.sh)
at `b3bd929`), does anything leave the container between `docker run` and its first request?

## What changes, and nothing else

- The script on the Jetson is replaced by the repo's `b3bd929` version (one added line, `-e DISABLE_VERSION_CHECK=True`,
  and that name added to the inspect grep). Same image, cache volume, key file.
- Jeremy starts the same capture (`tcpdump -i any -n 'not port 22 and not host 127.0.0.1'`, his `sudo`), then runs
  `sudo ~/inference-server-up.sh`, and stops the capture at least 120 s after `/info` answers. No request is sent to
  the server during the capture. The LIDAR stack keeps running as it is.
- Same scorer (`tools/jetson/egress_summary.py`, `/22` prefixes, both Jetson addresses), one window: the whole
  capture. The container's own address (`172.17.0.2`) as source on `docker0` is the attribution for "from the container".

## Bars

- **VC1:** zero DNS queries for `api.github.com` and zero TCP connections from `172.17.0.2` to any non-LAN address
  in the whole capture. PASS / FAIL.
- **VC2:** the container answers `GET /info` on `127.0.0.1:9001` within 120 s of `docker run`, and its `docker inspect`
  line prints `DISABLE_VERSION_CHECK=True` beside the other flags. PASS / FAIL.

## Predictions, written before the run

1. VC1 PASS with 0 bytes: in the re-capture, the only container egress between a start and the first request was the
   two version-check connections (the usage collector does not connect until a request arrives; the plan lookup is
   cached in `usage.db`), so with the flag the container is silent until it is asked something.
2. VC2 PASS; `/info` takes about 60 s (the 20 s wait in the script is too short and says so).
3. The only non-LAN traffic in the capture is the host operating system's: `connectivity-check.ubuntu.com` every
   5 minutes per interface, possibly one NTP exchange. Nothing to Roboflow, because no request is made.
4. The model is still resident in the cache volume: nothing model-sized comes in.

## What gets written

- `docs/field-tests/2026-09-28-roboflow/version-check-capture.json`: the scorer's window, the container-sourced lines,
  the DNS names queried, the `/info` time, the inspect line, the commands.
- Results section 5, one paragraph after "Egress, re-capture": VC1, VC2, predictions checked one by one.
- DR-11: "version check off, capture pending" becomes what is verified.
- The handoff's next item 1(b) closed or rewritten to what remains.

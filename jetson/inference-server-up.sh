#!/bin/bash
# inference-server-up.sh: (re)start the Roboflow Inference container on the Jetson the way DR-11 requires.
# Run as: sudo ~/inference-server-up.sh   (Docker on this device needs root; the line is Jeremy's to run.)
#
# Every flag has a reason recorded in docs/DECISIONS.md and docs/field-tests/2026-09-28-roboflow-finetune-results.md,
# section 5:
#   --read-only, --cap-drop=ALL, --security-opt=no-new-privileges   the hardened form Roboflow documents
#   -p 127.0.0.1:9001:9001                                          loopback only; the client posts only here (DR-11)
#   --volume /opt/nvme/inference-cache:/tmp:rw                       model cache and Triton kernels on the NVMe
#   -e TRITON_CACHE_DIR=/tmp/triton-cache                            the read-only root breaks Triton otherwise (DR-12)
#   -e MAX_ACTIVE_MODELS=2                                           8 GB Orin Nano; a third model gave CUBLAS_STATUS_ALLOC_FAILED
#   -e ACTIVE_LEARNING_ENABLED=False                                 no frame goes back to the workspace
#   -e TELEMETRY_OPT_OUT=True                                        kept for documentation; inert in Inference 1.7.2
#   -e METRICS_ENABLED=False                                         stops the model-monitoring pingback, which posted a
#                                                                    record of every request to api.roboflow.com once a
#                                                                    minute (EG1, 2026-09-28); added 2026-09-28,
#                                                                    verified by the 2026-09-29 re-capture (EG1 PASS)
#   -e DISABLE_VERSION_CHECK=True                                    stops the GET to api.github.com (inference's
#                                                                    release check at import) seen twice per container
#                                                                    start in the 2026-09-29 capture; verified by the
#                                                                    container-start capture the same night (VC1: no
#                                                                    GitHub lookup, no connection)
#   -e YOLO_OFFLINE=True                                             stops ultralytics' is_online() at import, a TCP
#                                                                    handshake to 1.1.1.1:80 twice per container start
#                                                                    (VC1 FAIL, 2026-09-29); verified by the next
#                                                                    container-start capture (VC1, VC2 PASS: no packet
#                                                                    from the idle container to any non-LAN address in
#                                                                    32.6 minutes, no request sent)
# What still leaves with all of the above: the usage collector's aggregated record every ~10 s while inferring
# (API key in clear, hashed hostname and IP, model id, frame counts). No switch turns it off short of OFFLINE_MODE=True
# or a local sink (METRICS_COLLECTOR_BASE_URL); DR-11 records the decision to let it leave, for now (Jeremy,
# 2026-09-29).
# The API key comes from the invoking user's ~/.roboflow.env through --env-file and is never on the command line.
# Under sudo, ~ is /root, so the file is resolved from SUDO_USER (override with GUARDIAN_ENV_FILE=/path).
# The file must be owned by that user, readable, and accessible only to its owner (normally mode 0600).
# Check before stopping an existing container; never repair permissions or print file contents automatically.
set -euo pipefail
INVOKING_USER="${SUDO_USER:-$USER}"
ENV_FILE="${GUARDIAN_ENV_FILE:-$(getent passwd "$INVOKING_USER" | cut -d: -f6)/.roboflow.env}"
[ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || { echo "key file must be a regular file, not a symlink: $ENV_FILE" >&2; exit 1; }
[ -r "$ENV_FILE" ] || { echo "key file not readable: $ENV_FILE (run as sudo from jeremy's login, or set GUARDIAN_ENV_FILE)"; exit 1; }
INVOKING_UID="$(id -u "$INVOKING_USER")"
# GNU stat on the Jetson; BSD stat supports local validation on macOS.
FILE_METADATA="$(stat -c '%u %a' "$ENV_FILE" 2>/dev/null)" || FILE_METADATA="$(stat -f '%u %Lp' "$ENV_FILE")"
read -r FILE_UID FILE_MODE <<< "$FILE_METADATA"
[ "$FILE_UID" = "$INVOKING_UID" ] || { echo "key file must be owned by $INVOKING_USER: $ENV_FILE" >&2; exit 1; }
if [[ ! "$FILE_MODE" =~ ^[0-7]{1,4}$ ]] || (( (8#$FILE_MODE & 077) != 0 || (8#$FILE_MODE & 0400) == 0 )); then
  echo "key file must be owner-readable with no group or other permissions (use mode 0600): $ENV_FILE" >&2
  exit 1
fi
docker rm -f inference-server >/dev/null 2>&1 || true
docker run -d --name inference-server --runtime nvidia --read-only \
  -p 127.0.0.1:9001:9001 \
  --volume /opt/nvme/inference-cache:/tmp:rw \
  --env-file "$ENV_FILE" \
  -e TRITON_CACHE_DIR=/tmp/triton-cache \
  -e MAX_ACTIVE_MODELS=2 \
  -e ACTIVE_LEARNING_ENABLED=False \
  -e TELEMETRY_OPT_OUT=True \
  -e METRICS_ENABLED=False \
  -e DISABLE_VERSION_CHECK=True \
  -e YOLO_OFFLINE=True \
  --security-opt=no-new-privileges --cap-drop=ALL --cap-add=NET_BIND_SERVICE \
  roboflow/roboflow-inference-server-jetson-6.2.0:latest
sleep 20
# Print the settings that matter and nothing else (the env-file's key is filtered out by the grep).
docker inspect inference-server --format 'readonly={{.HostConfig.ReadonlyRootfs}} ports={{json .HostConfig.PortBindings}} {{join .Config.Env " "}}' \
  | tr ' ' '\n' | grep -E '^(readonly=|ports=|ACTIVE_LEARNING|TELEMETRY|TRITON|MAX_ACTIVE|METRICS_ENABLED|DISABLE_VERSION_CHECK|YOLO_OFFLINE)'
curl -s -m 10 http://127.0.0.1:9001/info || echo "server not answering yet; retry /info in a minute"
echo

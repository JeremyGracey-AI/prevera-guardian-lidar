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
#                                                                    start in the 2026-09-29 capture; added after that
#                                                                    capture, not yet verified by one
# What still leaves with all of the above: the usage collector's aggregated record every ~10 s while inferring
# (API key in clear, hashed hostname and IP, model id, frame counts). No switch turns it off short of OFFLINE_MODE=True
# or a local sink (METRICS_COLLECTOR_BASE_URL); that is DR-11's open decision, not this script's to make.
# The API key comes from the invoking user's ~/.roboflow.env through --env-file and is never on the command line.
# Under sudo, ~ is /root, so the file is resolved from SUDO_USER (override with GUARDIAN_ENV_FILE=/path).
set -euo pipefail
ENV_FILE="${GUARDIAN_ENV_FILE:-$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)/.roboflow.env}"
[ -r "$ENV_FILE" ] || { echo "key file not readable: $ENV_FILE (run as sudo from jeremy's login, or set GUARDIAN_ENV_FILE)"; exit 1; }
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
  --security-opt=no-new-privileges --cap-drop=ALL --cap-add=NET_BIND_SERVICE \
  roboflow/roboflow-inference-server-jetson-6.2.0:latest
sleep 20
# Print the settings that matter and nothing else (the env-file's key is filtered out by the grep).
docker inspect inference-server --format 'readonly={{.HostConfig.ReadonlyRootfs}} ports={{json .HostConfig.PortBindings}} {{join .Config.Env " "}}' \
  | tr ' ' '\n' | grep -E '^(readonly=|ports=|ACTIVE_LEARNING|TELEMETRY|TRITON|MAX_ACTIVE|METRICS_ENABLED|DISABLE_VERSION_CHECK)'
curl -s -m 10 http://127.0.0.1:9001/info || echo "server not answering yet; retry /info in a minute"
echo

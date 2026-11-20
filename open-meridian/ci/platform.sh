#!/bin/bash
# The platform-master stand-in: core's plugin harness's `platform.py`, from the
# published harness image pinned by tag and digest (the one plugin-ecb's e2e
# pins), run on this machine. It holds a handful of currencies by their ISO 4217
# codes, so the deployment pulls the euro's and the dollar's cash instruments
# from it, as it would from the platform's master, and plugin-ecb's rates
# resolve. It is a test's stand-in, never a platform.
#
# Reads: HARNESS_IMAGE, RUN_DIR. Leaves it running, its log in RUN_DIR.
set -euo pipefail
: "${HARNESS_IMAGE:?}" "${RUN_DIR:?}"
id=$(docker create "$HARNESS_IMAGE" none)
docker cp "$id:/harness/platform.py" "$RUN_DIR/platform.py"
docker rm "$id" >/dev/null
nohup python3 -u "$RUN_DIR/platform.py" >"$RUN_DIR/platform.log" 2>&1 &
echo $! >"$RUN_DIR/platform.pid"
for _ in $(seq 1 50); do
  if curl -fs -o /dev/null "http://127.0.0.1:8000/api/v1/reference/licence-list"; then
    echo "platform: the stand-in answers on port 8000"
    exit 0
  fi
  sleep 0.2
done
echo "platform: the stand-in did not answer in 10s" >&2
cat "$RUN_DIR/platform.log" >&2
exit 1

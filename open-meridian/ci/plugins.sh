#!/bin/bash
# The run's two plugins, made the way a person makes them with the released CLI:
# `meridian connect` (the person allows it in a browser: connect.py), then
# `upload` (built here with docker, into the deployment's own registry) and
# `launch` of each:
#   - plugin-ecb at a pinned commit, holding `data`, as instance `ecb`: the
#     ECB's reference rates, public and keyless;
#   - this fork's plugin, holding `reporting`, as instance `workspace`, its
#     front end built first (frontend.sh).
#
# Reads: RUN_DIR, KUBECONFIG, ECB_REPO, ECB_REV.
set -euo pipefail
: "${RUN_DIR:?}" "${KUBECONFIG:?}" "${ECB_REPO:?}" "${ECB_REV:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD=http://meridian.localhost

git init -q "$RUN_DIR/plugin-ecb"
git -C "$RUN_DIR/plugin-ecb" fetch -q --depth 1 "$ECB_REPO" "$ECB_REV"
git -C "$RUN_DIR/plugin-ecb" checkout -q FETCH_HEAD

meridian connect "$DASHBOARD" >"$RUN_DIR/connect.log" 2>&1 &
connecting=$!
python3 "$HERE/connect.py" "$RUN_DIR/connect.log" "$RUN_DIR/person.json" "$DASHBOARD"
wait "$connecting" || { echo "plugins: meridian connect failed" >&2; sed -E 's/(code|state|code_challenge)=[^&[:space:]]*/\1=…/g' "$RUN_DIR/connect.log" >&2; exit 1; }

meridian plugin upload --dir "$RUN_DIR/plugin-ecb"
meridian plugin upload --dir "$HERE/../plugin"
meridian plugin launch ecb "$(sed -n 's/^version = "\(.*\)"/\1/p' "$RUN_DIR/plugin-ecb/pyproject.toml")" --instance ecb --yes
meridian plugin launch workspace "$(sed -n 's/^version = "\(.*\)"/\1/p' "$HERE/../plugin/pyproject.toml")" --instance workspace --yes
for instance in ecb workspace; do
  echo "plugins: waiting for ${instance}, at most 600s"
  kubectl -n meridian wait --for=condition=Available --timeout=600s "deployment/meridian-meridian-runtime-plugin-${instance}"
done
meridian plugin list

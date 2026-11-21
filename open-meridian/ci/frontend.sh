#!/bin/bash
# FINOS Workspace's front end, built for the plugin's image into
# open-meridian/plugin/web, inside containers (frontend.Dockerfile): upstream's
# own build with VITE_OPEN_MERIDIAN=true, which leaves out its sign-in, 2FA,
# password reset, admin area and AI library; then the schema of widgets.json
# with the built-in types alone, and the notices of every package the build
# ships, refused if any is under a GPL-family licence.
#
# Run from anywhere in the repository. Needs Docker, nothing else: the Node
# and the Python that build it are the images', pinned by digest.
set -euo pipefail
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
OUT="$ROOT/open-meridian/plugin/web"

# What a build before this one left is gone first, so web/ holds this build's
# files alone; a failed build leaves no web/, which the plugin's image refuses.
rm -rf "$OUT"
docker build -f "$ROOT/open-meridian/ci/frontend.Dockerfile" --output "type=local,dest=$OUT" "$ROOT"
# The exporter makes web/ itself readable by its owner alone; the plugin's
# image runs as another user, which reads every file of it.
chmod -R u+rwX,go+rX "$OUT"
test -s "$OUT/index.html" && test -s "$OUT/NOTICES.txt" && test -s "$OUT/widgets-schema.json"
echo "frontend: built into open-meridian/plugin/web ($(ls "$OUT" | wc -l | tr -d ' ') files)"

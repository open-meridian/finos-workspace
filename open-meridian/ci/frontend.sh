#!/bin/bash
# FINOS Workspace's front end, built for the plugin's image into
# open-meridian/plugin/web: upstream's own build (as frontend/Dockerfile runs
# it) with VITE_OPEN_MERIDIAN=true, which leaves out its sign-in, 2FA,
# password reset, admin area and AI library; then the schema of widgets.json
# with the built-in types alone, and the notices of every package the build
# ships, refused if any is under a GPL-family licence.
#
# Run from anywhere in the repository. Needs Node (frontend/package.json's
# engines) and Python 3.
set -euo pipefail
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
OUT="$ROOT/open-meridian/plugin/web"

(cd "$ROOT/frontend" \
  && npm ci --ignore-scripts --no-audit --no-fund \
  && VITE_OPEN_MERIDIAN=true node node_modules/vite/bin/vite.js build --mode runtime)
rm -rf "$OUT"
cp -R "$ROOT/frontend/dist" "$OUT"
rm -f "$OUT/config.js"

# What the build leaves out is not in the image: no chunk of those pages.
left=$(ls "$OUT" | grep -E '^(login|resetPassword|2fa|aiLibrary|LayoutAdmin)\.' || true)
if [ -n "$left" ]; then
  echo "frontend: the build still carries $left" >&2
  exit 1
fi

(cd "$ROOT" && python3 open-meridian/ci/widgets_schema.py "$OUT/widgets-schema.json")
node "$ROOT/open-meridian/ci/notices.mjs" "$ROOT/frontend" "$OUT/NOTICES.txt"
echo "frontend: built into open-meridian/plugin/web ($(ls "$OUT" | wc -l | tr -d ' ') files)"

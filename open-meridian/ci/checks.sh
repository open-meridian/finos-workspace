#!/bin/bash
# What this fork adds, held to its rules. Run from the repository's root.
#
# 1. Upstream: every upstream file this branch changes is listed in
#    open-meridian/PROVENANCE.md, and upstream's LICENSE and NOTICE are unchanged.
# 2. Names: nothing we add names a persona, a private sample or an internal name.
# 3. Licences: nothing we add carries an AGPL or GPL notice; the provenance file is there.
# 4. No route out: the wrapper's code holds no HTTP client and no socket; it
#    reaches only its sidecar, through the SDK.
set -euo pipefail
failed=0
fail() { echo "checks: $*" >&2; failed=1; }
base="${BASE_REF:-origin/open-meridian}"
ours=(open-meridian .github/workflows/open-meridian.yml)

# 1. Upstream.
while IFS= read -r changed; do
  case "$changed" in open-meridian/*|.github/workflows/open-meridian.yml|README.md) continue ;; esac
  grep -qF "\`$changed\`" open-meridian/PROVENANCE.md || fail "upstream's $changed changes and PROVENANCE.md does not list it"
done < <(git diff --name-only "$base"...HEAD)
git diff --quiet "$base"...HEAD -- LICENSE NOTICE LICENSE.spdx || fail "upstream's licence or notice files changed"

# 2. Names.
if grep -RIniE 'persona|researcher|plugin-sample|sample-(fx|multi-asset|options|pricing|reporting|operations)|discretionary pm|systematic pm' \
     "${ours[@]}" --exclude=checks.sh --exclude-dir=web --exclude-dir=.venv; then
  fail "a persona, a private sample or an internal name appears in what we add"
fi

# 3. Licences.
if grep -RIlE 'GNU (Affero )?General Public License|AGPL-3|SPDX-License-Identifier: *(A?GPL)' \
     "${ours[@]}" --exclude=checks.sh --exclude-dir=web --exclude-dir=.venv; then
  fail "an AGPL or GPL notice in what we add"
fi
grep -q 'Apache License' LICENSE || fail "upstream's Apache-2.0 licence is not at LICENSE"
[ -f open-meridian/PROVENANCE.md ] || fail "open-meridian/PROVENANCE.md is missing"

# 4. No route out.
if grep -RnE '^\s*(import|from) (urllib\.request|http\.client|socket|requests|httpx|aiohttp)\b' open-meridian/plugin/src; then
  fail "the wrapper imports an HTTP client or a socket: it reaches only its sidecar"
fi

[ "$failed" -eq 0 ] && echo "checks: upstream changes listed, names, licences and no route out hold"
exit "$failed"

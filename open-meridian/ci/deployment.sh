#!/bin/bash
# A local Open Meridian deployment on a k3d cluster made for this run, from the
# released CLI and the released chart, both pinned by the workflow (as
# open-meridian/opencode#1's ci/deployment.sh does it), with two dashboard
# copies (values.yaml) and the platform stand-in (platform.sh) as its platform.
#
# `meridian up` installs it at http://meridian.localhost: plain HTTP on a name
# under .localhost, which Chromium sends to this machine by itself, as it does
# each plugin's host, {instance}.plugins.meridian.localhost.
#
# Reads: CHART_VERSION, K3S_IMAGE, KUBECONFIG (written here), RUN_DIR.
set -euo pipefail
: "${CHART_VERSION:?}" "${K3S_IMAGE:?}" "${KUBECONFIG:?}" "${RUN_DIR:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CLUSTER=workspace
READY_SECONDS=300

ready() {
  local what="$1"; shift
  local start=$SECONDS
  echo "deployment: waiting for ${what}, at most ${READY_SECONDS}s"
  until "$@" >/dev/null 2>&1; do
    if (( SECONDS - start >= READY_SECONDS )); then
      echo "deployment: gave up on ${what}" >&2
      kubectl get pods -A -o wide >&2 || true
      return 1
    fi
    sleep 2
  done
}

k3d cluster create "$CLUSTER" --image "$K3S_IMAGE" -p "80:80@loadbalancer" \
  --kubeconfig-update-default=false --kubeconfig-switch-context=false \
  --wait --timeout "${READY_SECONDS}s"
k3d kubeconfig get "$CLUSTER" >"$KUBECONFIG"
chmod 600 "$KUBECONFIG"

ready "the API server" kubectl get --raw /readyz
ready "the default service account" kubectl -n default get serviceaccount default
ready "k3s's own deployments to be available" \
  kubectl -n kube-system wait --for=condition=Available --timeout=10s \
  deployment coredns local-path-provisioner metrics-server traefik
ready "every API group" kubectl api-resources
ready "an ingress class" sh -c 'kubectl get ingressclass -o name | grep -q .'

# A syntactically valid identifier and code that no platform issued: nothing
# here enrols. The platform is the stand-in on this machine, which k3d names
# host.k3d.internal inside the cluster.
export MERIDIAN_ENROLMENT_CODE="ENR-P2CI-P2CI-P2CI"
meridian up --id DEP-00000000000000000000000000 --no-doctor --no-archive --plain-http \
  --chart-version "$CHART_VERSION" --platform http://host.k3d.internal:8000 \
  -f "$HERE/values.yaml" 2>&1 | tee "$RUN_DIR/meridian-up.log"

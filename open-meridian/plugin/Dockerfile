# The plugin's image: the SDK's base for the release pyproject.toml pins, the
# wrapper, and FINOS Workspace's front end built beside it (web/, which
# open-meridian/ci/frontend.sh writes before an upload). Nothing else of
# upstream's is in it: no backend-api, no database, no Valkey, no agent.
ARG BASE=ghcr.io/open-meridian/plugin-python:0.37.1@sha256:cb612e16262390c5dc71ee976731bd74d2c693455aef788ab36fcfd3d16291c2
FROM ${BASE}
WORKDIR /plugin
COPY . .
RUN test -s web/index.html && test -s web/NOTICES.txt && pip install --no-cache-dir .
USER 65532
CMD ["workspace"]

# FINOS Workspace's front end, built in containers, so a person building the
# plugin needs Docker and nothing else:
# - Node: upstream's own build (as frontend/Dockerfile runs it) with
#   VITE_OPEN_MERIDIAN=true, which leaves out its sign-in, 2FA, password
#   reset, admin area and AI library, refused if a chunk of those pages is
#   left; then the notices of every package the build ships, refused if any
#   is under a GPL-family licence (notices.mjs);
# - Python: the schema of widgets.json with the built-in types alone, by
#   upstream's own code (widgets_schema.py).
# Any of these failing fails the build, and nothing is written.
#
# Built from the repository's root, where upstream's frontend/ and
# backend-api/ sit and stay, by open-meridian/ci/frontend.sh, which exports
# the last stage, the built files alone, into open-meridian/plugin/web. Each
# COPY names what it takes; frontend.Dockerfile.dockerignore keeps a
# node_modules or dist left in frontend/ out.
ARG NODE=node:26.12.1-trixie-slim@sha256:94816674c62774da0d099a947bf4613b9e1972a2733abd0d0cd80e795f8411d0
ARG PYTHON=python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

FROM ${NODE} AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN VITE_OPEN_MERIDIAN=true node node_modules/vite/bin/vite.js build --mode runtime && rm -f dist/config.js
# What the build leaves out is not in the image: no chunk of those pages.
RUN left=$(ls dist | grep -E '^(login|resetPassword|2fa|aiLibrary|LayoutAdmin)\.' || true); \
    if [ -n "$left" ]; then echo "frontend: the build still carries $left" >&2; exit 1; fi
COPY open-meridian/ci/notices.mjs /src/open-meridian/ci/notices.mjs
RUN node /src/open-meridian/ci/notices.mjs /src/frontend dist/NOTICES.txt

FROM ${PYTHON} AS schema
WORKDIR /src
COPY backend-api/backend/api/widget_plugins/widgets_schema.py backend-api/backend/api/widget_plugins/widgets_schema_kit.json backend-api/backend/api/widget_plugins/
COPY open-meridian/ci/widgets_schema.py open-meridian/ci/widgets_schema.py
RUN python3 open-meridian/ci/widgets_schema.py /widgets-schema.json

FROM scratch
COPY --from=build /src/frontend/dist/ /
COPY --from=schema /widgets-schema.json /widgets-schema.json

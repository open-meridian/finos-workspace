# Provenance

This branch, `open-meridian`, adds an Open Meridian plugin to FINOS Workspace
(Apache-2.0). Upstream's default branch is untouched. This file lists where
each part of what we add comes from, and every upstream file we change.

## What we add

| Path | What | From |
|---|---|---|
| `open-meridian/plugin/` | The plugin: the wrapper that serves Workspace's front end, answers the part of its `/app` API the front end calls, and answers its widgets from the lake through the plugin's sidecar | Written here, on the Open Meridian SDK (`open-meridian==0.37.1`, Apache-2.0) |
| `open-meridian/plugin/src/workspace/apps.json` | The starter dashboard | Written here, in the format of upstream's `docs/reference/schemas/apps-json.mdx` |
| `open-meridian/plugin/src/workspace/theme.css` | Workspace's accent, status and type mapped onto Open Meridian's UI kit tokens | Written here; the kit is served by the deployment's dashboard |
| `open-meridian/ci/first_run.py` | First run for the CI deployment, with no platform | open-meridian/opencode@08c9ffe1e349737dbd85ce8d07f231a737ebf0d1 `open-meridian/ci/first_run.py` (written by Open Meridian), with a second person added |
| `open-meridian/ci/deployment.sh` | A k3d deployment from the released CLI and chart | The same commit's `open-meridian/ci/deployment.sh`, with two dashboard copies and the platform stand-in |
| `open-meridian/ci/connect.py` | The person allows `meridian connect` | open-meridian/meridian-desktop's `ci/connect.mjs`, in Python |
| `open-meridian/ci/platform.sh` | Runs the platform-master stand-in | Runs `platform.py` from core's published harness image (`ghcr.io/open-meridian/meridian-harness`, pinned by digest in the workflow) |
| `open-meridian/ci/widgets_schema.py` | The schema of `widgets.json` with the built-in types alone | Runs upstream's own `backend-api/backend/api/widget_plugins/widgets_schema.py` on upstream's kit, its database imports left out |
| `open-meridian/ci/*` (the rest), `.github/workflows/open-meridian.yml` | The fork's checks and CI job | Written here |

No code from any other reference project is used. There is no clean-room
part in this branch.

## Licences of what the plugin's image ships

- Workspace's front end, built from upstream's `frontend/` (Apache-2.0), with
  `NOTICES.txt` beside it in the image: upstream's `LICENSE` and `NOTICE`
  first, then the licence and notice files of every package the build ships.
  `open-meridian/ci/notices.mjs` writes it, and fails the build on a package
  under the AGPL, the GPL or the SSPL, one whose licence is unstated or
  `UNLICENSED`, or `dockview-enterprise`.
- The wrapper's Python: the Open Meridian SDK (`open-meridian`, Apache-2.0)
  and what it requires, each distribution's licence in its own metadata in
  the image. `open-meridian/ci/python_licences.py` lists them in CI and
  fails on the same licences.
- Dockview: none of its packages is used, its MIT ones or any other.
- Charts: no chart library is shipped. The rates chart is an SVG the plugin
  draws itself (`open-meridian/plugin/src/workspace/widgets.py`), under this
  fork's Apache-2.0.

## Upstream files we change

Each change is the least the plugin needs, and builds the same as upstream
unless `VITE_OPEN_MERIDIAN=true` is set at build time.

- `README.md`: the fork's opening section.
- `frontend/src/main.tsx`: with `VITE_OPEN_MERIDIAN=true`, the routes of
  Workspace's own sign-in, password reset, 2FA, OAuth callback, admin area and
  AI library are left out of the build, and their lazy imports marked pure so
  their files are not built: the deployment signs people in and holds their
  access, and the agent surface is off.
- `frontend/src/components/LayoutAuth/AuthSidebar.tsx`: with the same flag,
  the sidebar's link to the AI library is left out.

## How the `/app` subset was found

The built front end was loaded in a browser against the wrapper, which logs
every `/app` route it does not serve, and taken through start, the Apps page,
opening the starter dashboard and its widgets, and the Widgets library. It
called seven routes of upstream's backend-api's 95 under `/app`:
`GET /app/session`, `GET /app/dash/validate-and-sync`,
`GET /app/data-connectors/api-source`,
`POST /app/data-connectors/api-source/{id}/request`,
`GET /app/resource-permissions`, `GET /app/widget-plugins` and
`GET /app/widget-plugins/widgets-schema`; and `GET /app/custom-copilot`,
which is answered 404. The wrapper also answers `POST /app/dash/sync` and
`POST /app/display-settings` (saved nowhere) and refuses any change to the
one connection. `open-meridian/plugin/tests/test_wrapper.py` holds the list.

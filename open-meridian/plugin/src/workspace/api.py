"""The part of Workspace's `/app` API the front end calls, answered here.

Workspace's backend-api is not in the image (decisions/028): no database, no
Valkey, no account. This answers the routes the front end calls at start
and on the dashboard screens, each from the page request's assertion:

- the session (`/app/session`, `/app/user`, `/app/access`): the person the
  dashboard vouched for, with no Workspace account behind them and nothing
  kept after the request;
- dashboards (`/app/dash/sync`): the starter dashboards come from the
  connection's `apps.json`; a person's own changes live in their browser
  for the session, and a save is answered and kept nowhere;
- connections: one, fixed, the lake (`/app/data-connectors/api-source`),
  which a person cannot add to, change or remove;
- widget requests to it (`/app/data-connectors/api-source/{id}/request`),
  answered in process (widgets.py).

Every other `/app` route is answered 404: sign-in, 2FA and password reset,
the admin area, roles and sharing, files, the copilot and its keys,
custom copilots, MCP servers, the MCP proxy and OAuth, Workspace MCP and
its tokens, widget plugins and usage. `NEVER` names them for the tests.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import meridian

from . import widgets
from .lake import Lake

log = logging.getLogger("workspace")

#: Where the front end reaches the `/app` API: a path on the page's own origin.
PREFIX = "/api"

#: `widgets.json`'s schema, built beside the front end.
SCHEMA = Path("/plugin/web/widgets-schema.json")

#: Routes of Workspace's API this never serves, by their path's start: the
#: spec's "never served" and "not in the image" lists.
NEVER = (
    "/app/login",
    "/app/logout",
    "/app/google-auth",
    "/app/sign-in",
    "/app/2fa",
    "/app/reset-password",
    "/app/validate",
    "/app/copilot",
    "/app/copilot-chats",
    "/app/copilot-keys",
    "/app/custom-copilot",
    "/app/mcp-servers",
    "/app/mcp-proxy",
    "/app/mcp-oauth",
    "/app/workspace-mcp",
    "/app/workspace-tools",
    "/app/files",
    "/app/usage",
    "/app/widget-plugins/report",
    "/app/user-apps",
    "/app/skills",
    "/app/prompts",
    "/admin",
    "/entity",
    "/plugins",
    "/user",
    "/totp",
    "/internal",
    "/.well-known",
)

DISPLAY_SETTINGS = {
    "theme": "dark",
    "showWidgetControlsEllipsis": True,
    "aiEnhancements": False,
    "fontSize": "medium",
    "gridCorners": ["se"],
    "gridSnapping": "off",
    "quickAddButtonVisible": True,
    "showMinimizeButton": False,
}

#: What a person may do in Workspace's own terms: use dashboards, add no
#: connection, share nothing.
ACCESS = {"user_type": "User", "sharing": "none"}


@dataclass(frozen=True)
class Answer:
    status: int
    content_type: str
    body: bytes


def _json(data: Any, status: int = 200) -> Answer:
    return Answer(status, "application/json", json.dumps(data).encode())


def _person(caller: meridian.Caller) -> dict[str, Any]:
    """The session's person as Workspace's front end reads one: from the
    assertion alone, kept nowhere. The subject stands where an email would;
    no address is invented for anybody."""
    shown = caller.display_name or caller.subject
    first, _, last = shown.partition(" ")
    return {
        "uuid": caller.subject,
        "email": caller.subject,
        "username": shown,
        "entity_name": None,
        "role": None,
        "access": ACCESS,
        "usage": None,
        "temporary_password": False,
        "force_2fa": False,
        "user": {"first_name": first, "last_name": last, "display_settings": DISPLAY_SETTINGS},
    }


def _sync() -> dict[str, Any]:
    """What `/app/dash/sync` answers: no dashboard of the person's own, the
    one connection, no file, no copilot."""
    return {
        "owned": {},
        "shared": {},
        "entity_shared": {},
        "entity_theme_settings": {},
        "access": ACCESS,
        "copilot_chats": [],
        "questions_history": [],
        "display_settings": DISPLAY_SETTINGS,
        "file_widgets": [],
        "widget_metadata": [],
        "user_skills": [],
        "mcp_servers": [],
    }


Handler = Callable[[Lake, meridian.Caller, str, dict[str, Any]], Awaitable[Answer]]


async def _session(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json(_person(caller))


async def _access(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json(ACCESS)


async def _dash_sync(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json(_sync())


async def _saved_nowhere(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    """A save the front end sends: answered, and kept nowhere (no saved
    dashboards in the first slice)."""
    return _json({"success": True})


async def _sources(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json([widgets.source()])


async def _source_request(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    if not isinstance(body, dict) or not isinstance(body.get("url"), str):
        return _json({"detail": "A widget request names its url."}, 422)
    status, content_type, data = await widgets.request(lake, body["url"])
    return Answer(status, content_type, data)


async def _fixed(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json({"detail": "This workspace's one connection is fixed."}, 403)


async def _empty_list(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json([])


async def _permissions(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    """No backend, file or prompt shared with the person: the one
    connection is everybody's, and nothing else exists here."""
    return _json({"backends": [], "files": [], "prompts": []})


async def _no_widget_plugins(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    """Widget plugins are not in the image: none, and the feature off."""
    return _json({"enabled": False, "etag": "none", "plugins": [], "vizHandlers": {}})


async def _widgets_schema(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    """The schema of `widgets.json` with Workspace's built-in types alone,
    which the image's build composed from upstream's own kit with no widget
    plugin (open-meridian/ci/widgets_schema.py)."""
    return Answer(200, "application/json", SCHEMA.read_bytes())


async def _theme(lake: Lake, caller: meridian.Caller, path: str, body: Any) -> Answer:
    return _json({})


SOURCE = re.escape(widgets.SOURCE_ID)

#: (method, path pattern) → handler: the whole subset.
ROUTES: list[tuple[str, re.Pattern[str], Handler]] = [
    ("GET", re.compile(r"/app/session"), _session),
    ("GET", re.compile(r"/app/user"), _session),
    ("GET", re.compile(r"/app/access"), _access),
    ("GET", re.compile(r"/app/dash/(validate-and-)?sync(/owned|/shared)?"), _dash_sync),
    ("GET", re.compile(r"/app/resource-permissions"), _permissions),
    ("GET", re.compile(r"/app/widget-plugins"), _no_widget_plugins),
    ("GET", re.compile(r"/app/widget-plugins/widgets-schema"), _widgets_schema),
    ("POST", re.compile(r"/app/dash/sync"), _saved_nowhere),
    ("POST", re.compile(r"/app/display-settings"), _saved_nowhere),
    ("GET", re.compile(r"/app/theme-settings"), _theme),
    ("GET", re.compile(r"/app/widget-metadata"), _empty_list),
    ("GET", re.compile(r"/app/data-connectors/api-source"), _sources),
    ("GET", re.compile(r"/app/data-connectors/file"), _empty_list),
    ("POST", re.compile(rf"/app/data-connectors/api-source/{SOURCE}/request"), _source_request),
    ("POST", re.compile(r"/app/data-connectors/api-source/[^/]+"), _fixed),
    ("DELETE", re.compile(r"/app/data-connectors/api-source/[^/]+"), _fixed),
    ("PUT", re.compile(r"/app/data-connectors/api-source/[^/]+/mcp-servers"), _fixed),
    ("POST", re.compile(r"/app/data-connectors/api-source-test/request"), _fixed),
]


def never(path: str) -> bool:
    return any(path == each or path.startswith(each + "/") for each in NEVER)


def served(method: str, path: str) -> bool:
    """Whether the subset answers this route: the tests' list of it."""
    return not never(path) and any(
        verb == method and pattern.fullmatch(path) for verb, pattern, _ in ROUTES
    )


async def answer(lake: Lake, caller: meridian.Caller, method: str, path: str, body: bytes) -> Answer:
    """One request to the `/app` API, by its path under PREFIX."""
    if not never(path):
        for verb, pattern, handler in ROUTES:
            if verb == method and pattern.fullmatch(path):
                try:
                    parsed = json.loads(body) if body else {}
                except ValueError:
                    return _json({"detail": "The body is not JSON."}, 400)
                return await handler(lake, caller, path, parsed)
    log.info("not served: %s %s", method, path)
    return _json({"detail": "Not served in this workspace."}, 404)

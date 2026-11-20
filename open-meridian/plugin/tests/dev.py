"""The wrapper on this machine, against the stand-in sidecar, for a browser:
every request is given the `Meridian-Caller` header a sidecar would forward,
for Ada in a session at the level asked (WORKSPACE_LEVEL, `read` unless
said). For the browser check and for finding what the front end asks;
never a way to run the plugin.

    WORKSPACE_WEB=<built front end> python tests/dev.py [port]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from pathlib import Path

from meridian.pages import _serve
from meridian.testing import caller_header

sys.path.insert(0, os.path.dirname(__file__))

from standin import Sidecar  # noqa: E402

from workspace import api  # noqa: E402
from workspace import api  # noqa: E402
from workspace.lake import Lake  # noqa: E402
from workspace.pages import pages, use  # noqa: E402


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    sidecar = Sidecar(entitled=os.environ.get("WORKSPACE_ENTITLED", "1") == "1")
    use(sidecar.bind(Lake()))
    pages.web = Path(os.environ["WORKSPACE_WEB"])
    api.SCHEMA = pages.web / "widgets-schema.json"
    pages.web = Path(os.environ["WORKSPACE_WEB"])
    api.SCHEMA = pages.web / "widgets-schema.json"
    header = caller_header(os.environ.get("WORKSPACE_LEVEL", "read")).encode()
    app = pages.app(sidecar)

    async def with_caller(scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope, headers=[*scope["headers"], (b"meridian-caller", header)])
        await app(scope, receive, send)

    async def run() -> None:
        _serve(with_caller, port, asyncio.get_running_loop(), pages.max_body)
        print(f"dev: http://127.0.0.1:{port}/", flush=True)
        await asyncio.Event().wait()

    asyncio.run(run())


if __name__ == "__main__":
    main()

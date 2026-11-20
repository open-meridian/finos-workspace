"""What this plugin declares about itself: the reporting role's common
setting, its two pages, and its documentation (`docs/`, at `/plugin/docs` in
its image). A version registers exactly the declaration it was uploaded with:
the port is fixed here."""

from __future__ import annotations

import meridian
from meridian.roles import reporting

from .pages import TITLE, pages

#: The port its page is served on, on loopback, where its sidecar forwards.
PORT = 8000

DECLARATION = meridian.Declaration(
    settings=[reporting.reporting_currency()],
    interface=meridian.Interface(port=PORT, title=TITLE, pages=pages),
    documentation="docs",
)

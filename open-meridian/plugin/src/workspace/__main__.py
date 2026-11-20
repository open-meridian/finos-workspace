"""Runs the plugin: its reporting role class on the sidecar it is launched
beside, and its page. Everything it reads goes through that sidecar."""

import logging

import meridian

from .declaration import DECLARATION, PORT
from .lake import Lake
from .pages import pages, use


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    lake = Lake()
    use(lake)
    meridian.run(declaration=DECLARATION, roles=[lake], pages=pages, port=PORT)


if __name__ == "__main__":
    main()

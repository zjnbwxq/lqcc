"""Compatibility helpers for LQCC automation.

The public implementation lives in lqcc.automation. This module keeps the
small test/import surface stable for users who want to create an in-process
server.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from os import PathLike

from .automation import ServerConfig, make_handler


def make_daemon_server(capsule: str | PathLike[str], *, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Return a local LQCC daemon server without starting serve_forever()."""
    config = ServerConfig(capsule=str(capsule), host=host, port=port)
    return ThreadingHTTPServer((host, int(port)), make_handler(config))

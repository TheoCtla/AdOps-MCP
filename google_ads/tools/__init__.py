"""Enregistrement des tools Google Ads sur le server MCP.

Ce sous-package agrège les groupes de tools (``read`` aujourd'hui,
``write`` plus tard) et expose une unique fonction ``register_all_tools``
que ``server.py`` appelle au démarrage.
"""

from __future__ import annotations

from mcp.server import Server

from google_ads.tools.read import register_read_tools


def register_all_tools(server: Server) -> None:
    """Enregistre tous les tools Google Ads (lecture + écriture) sur le server."""
    register_read_tools(server)
    # register_write_tools(server) — sera ajouté plus tard.

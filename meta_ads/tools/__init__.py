"""Enregistrement des tools Meta Ads sur le server MCP."""

from __future__ import annotations

from mcp.server import Server

from meta_ads.tools.read import register_meta_read_tools
from meta_ads.tools.write import register_meta_write_tools


def register_all_meta_tools(server: Server) -> None:
    """Enregistre tous les tools Meta Ads (lecture + écriture) sur le server."""
    register_meta_read_tools(server)
    register_meta_write_tools(server)

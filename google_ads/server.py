"""Point d'entrée du serveur MCP Tarmaac — Google Ads + Meta Ads.

Transports supportés (via la variable d'env ``MCP_TRANSPORT``) :
- ``stdio`` (défaut) : dev local, branché sur Claude Code / MCP Inspector.
- ``http`` : HTTP/SSE pour la production derrière un reverse proxy (Caddy).
  Port configurable via ``MCP_PORT`` (défaut 8000).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from google_ads.tools import register_all_tools
from meta_ads.tools import register_all_meta_tools


log = logging.getLogger("tarmaac.mcp")


def build_server() -> Server:
    """Construit le server MCP, enregistre les tools et câble le dispatcher.

    Le dispatcher (``list_tools`` / ``call_tool``) lit le registre mutualisé
    attaché au server par les fonctions ``register_*_tools``.
    En mode dev local (stdio), les tools Google Ads et Meta Ads coexistent
    dans le même serveur.
    """
    server: Server = Server("tarmaac-mcp")
    register_all_tools(server)
    register_all_meta_tools(server)

    registry = getattr(server, "_tarmaac_registry", {"tools": [], "handlers": {}})

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return list(registry["tools"])

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        handler = registry["handlers"].get(name)
        if handler is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": f"Tool inconnu : {name}"}, ensure_ascii=False
                    ),
                )
            ]
        return await handler(arguments or {})

    return server


async def main() -> None:
    # IMPORTANT : les logs DOIVENT aller sur stderr. stdout est réservé aux
    # messages JSON-RPC du transport MCP stdio ; tout print() sur stdout
    # casserait le protocole.
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    server = build_server()

    if transport == "http":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )

        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )

        port = int(os.environ.get("MCP_PORT", "8000"))
        log.info("Tarmaac MCP server starting (http) on 0.0.0.0:%s — Google Ads + Meta Ads", port)

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level=os.environ.get("LOG_LEVEL", "info").lower())
        srv = uvicorn.Server(config)
        await srv.serve()
        return

    from mcp.server.stdio import stdio_server

    log.info("Tarmaac MCP server starting (stdio) — Google Ads + Meta Ads")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())

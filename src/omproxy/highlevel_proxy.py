# MIT License
# Copyright (c) 2024 Sergey Parfenyuk
# see https://github.com/sparfenyuk/mcp-proxy/blob/main/LICENSE
"""Create a local server that proxies requests to a remote server over stdio."""

import logfire
import logging
import typing as t

from mcp import StdioServerParameters, server, types
from mcp.client.session import ClientSession


logger = logging.getLogger(__name__)


async def create_proxy_server(remote_app: ClientSession) -> server.Server:  # noqa: C901
    """Create a server instance from a remote app."""

    response = await remote_app.initialize()
    capabilities = response.capabilities
    app = server.Server(response.serverInfo.name)

    if capabilities.prompts:

        async def _list_prompts(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            result = await remote_app.list_prompts()
            return types.ServerResult(result)

        app.request_handlers[types.ListPromptsRequest] = _list_prompts

        async def _get_prompt(req: types.GetPromptRequest) -> types.ServerResult:
            result = await remote_app.get_prompt(req.params.name, req.params.arguments)
            return types.ServerResult(result)

        app.request_handlers[types.GetPromptRequest] = _get_prompt

    if capabilities.resources:

        async def _list_resources(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            result = await remote_app.list_resources()
            return types.ServerResult(result)

        app.request_handlers[types.ListResourcesRequest] = _list_resources

        # list_resource_templates() is not implemented in the client
        # async def _list_resource_templates(_: t.Any) -> types.ServerResult:
        #     result = await remote_app.list_resource_templates()
        #     return types.ServerResult(result)

        # app.request_handlers[types.ListResourceTemplatesRequest] = _list_resource_templates

        async def _read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
            from omproxy.cli import instance_id_var

            with logfire.span(
                f"Reading resource '{req.params.uri}'",
                req=req,
                instance_id=instance_id_var.get(),
            ):
                result = await remote_app.read_resource(req.params.uri)
                return types.ServerResult(result)

        app.request_handlers[types.ReadResourceRequest] = _read_resource

    if capabilities.logging:

        async def _set_logging_level(req: types.SetLevelRequest) -> types.ServerResult:
            await remote_app.set_logging_level(req.params.level)
            return types.ServerResult(types.EmptyResult())

        app.request_handlers[types.SetLevelRequest] = _set_logging_level

    if capabilities.resources:

        async def _subscribe_resource(
            req: types.SubscribeRequest,
        ) -> types.ServerResult:
            await remote_app.subscribe_resource(req.params.uri)
            return types.ServerResult(types.EmptyResult())

        app.request_handlers[types.SubscribeRequest] = _subscribe_resource

        async def _unsubscribe_resource(
            req: types.UnsubscribeRequest,
        ) -> types.ServerResult:
            await remote_app.unsubscribe_resource(req.params.uri)
            return types.ServerResult(types.EmptyResult())

        app.request_handlers[types.UnsubscribeRequest] = _unsubscribe_resource

    if capabilities.tools:

        async def _list_tools(_: t.Any) -> types.ServerResult:  # noqa: ANN401
            tools = await remote_app.list_tools()
            return types.ServerResult(tools)

        app.request_handlers[types.ListToolsRequest] = _list_tools

        async def _call_tool(req: types.CallToolRequest) -> types.ServerResult:
            # prevent circular import
            from omproxy.cli import instance_id_var

            with logfire.span(
                f"Calling tool '{req.params.name}'",
                req=req,
                instance_id=instance_id_var.get(),
            ):
                try:
                    result = await remote_app.call_tool(
                        req.params.name,
                        (req.params.arguments or {}),
                    )
                    return types.ServerResult(result)
                except Exception as e:  # noqa: BLE001
                    logfire.exception(
                        "Error calling tool", instance_id=instance_id_var.get()
                    )
                    return types.ServerResult(
                        types.CallToolResult(
                            content=[types.TextContent(type="text", text=str(e))],
                            isError=True,
                        ),
                    )

        app.request_handlers[types.CallToolRequest] = _call_tool

    async def _send_progress_notification(req: types.ProgressNotification) -> None:
        await remote_app.send_progress_notification(
            req.params.progressToken,
            req.params.progress,
            req.params.total,
        )

    app.notification_handlers[types.ProgressNotification] = _send_progress_notification

    async def _complete(req: types.CompleteRequest) -> types.ServerResult:
        result = await remote_app.complete(
            req.params.ref,
            req.params.argument.model_dump(),
        )
        return types.ServerResult(result)

    app.request_handlers[types.CompleteRequest] = _complete

    return app


async def run_stdio_client(server_parameters: StdioServerParameters) -> None:
    """Run the stdio client.

    Args:
        server_parameters: The server parameters to use for stdio_client (contain mcp server to run).

    """
    from mcp.client.stdio import stdio_client

    # here we could setup SSE with sse_client instead see:
    # https://github.com/sparfenyuk/mcp-proxy/blob/c132722d667e7eaea3637947fcba5dc2d821ea69/src/mcp_proxy/__init__.py#L132

    # create the inner stdio_client and ClientSession.
    # stdio_client spawn a process running the mcp server based on server_parameters.
    # command, args, env to run the mcp server are usuallyy via cli in server_parameters.
    async with (
        stdio_client(server_parameters) as streams,
        ClientSession(*streams) as session,
    ):
        app = await create_proxy_server(session)
        async with server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
                # raise_exceptions=True,
            )

import sys

import anyio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import JSONRPCMessage

# define a transport (must be an async context manager)
# yielding a read_stream and write_stream like stdio_client or sse_client.
TRANSPORT_CLIENT = stdio_client


async def run_proxy(server_parameters: StdioServerParameters):
    # create a stdio client connected to a running subprocess with the MCP server
    # read_stream can be used to read messages from the MCP server
    # write_stream can be used to send messages to the MCP server
    async with TRANSPORT_CLIENT(server_parameters) as (read_stream, write_stream):

        async def forward_mcp_client_messages():
            """forward messages received on stdin from the MCP client to the MCP server"""
            stdin = anyio.wrap_file(sys.stdin)

            async for message in stdin:
                print(f"Proxy Received from MCP client: {message}", file=sys.stderr)

                message = JSONRPCMessage.model_validate_json(message)

                # upon receiving a message we forward it to the MCP server
                # the write stream of the MCP server excepts a JSONRPCMessage
                await write_stream.send(message)

                print(f"Proxy Sent to MCP server: {message}", file=sys.stderr)

        async def forward_mcp_server_messages():
            """forward messages received on stdout from the MCP server to the MCP client"""
            async for message in read_stream:
                print(f"Proxy Received from MCP server: {message}", file=sys.stderr)

                # TODO: handle exceptions (write JSONRPCError to stdout)

                # we forward the response from the MCP server
                # back to the original MCP client via stdout
                json = message.model_dump_json(by_alias=True, exclude_none=True)
                sys.stdout.write(json + "\n")
                sys.stdout.flush()

                print(f"Proxy Sent to MCP client: {json}", file=sys.stderr)

        async with anyio.create_task_group() as tg:
            tg.start_soon(forward_mcp_client_messages)
            tg.start_soon(forward_mcp_server_messages)


if __name__ == "__main__":
    # define end MCP server parameters
    server_parameters: StdioServerParameters = StdioServerParameters(
        command="uv",
        args=["run", "src/echo.py"],
    )

    anyio.run(run_proxy, server_parameters)

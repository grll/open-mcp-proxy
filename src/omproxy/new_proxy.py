import sys

import anyio
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import JSONRPCMessage


class Proxy:
    async def run(self, server_parameters: StdioServerParameters):
        """forward messages on stdin to a spawned MCP server and forward messages from the spawned MCP server to stdout"""
        # create a client connected to a running subprocess with the MCP server
        # read_stream can be used to read messages from the MCP server
        # write_stream can be used to send messages to the MCP server
        async with stdio_client(server_parameters) as (read_stream, write_stream):
            try:

                async def forward_mcp_client_messages():
                    """forward messages received on stdin from the MCP client to the MCP server"""
                    stdin = anyio.wrap_file(sys.stdin)

                    async for message in stdin:
                        print(
                            f"Proxy Received from MCP client: {message}",
                            file=sys.stderr,
                        )

                        # TODO: handle exceptions if we fail to parse message from client.
                        message = JSONRPCMessage.model_validate_json(message)

                        self._on_mcp_client_message(message)

                        # upon receiving a message we forward it to the MCP server
                        # the write stream of the MCP server excepts a JSONRPCMessage
                        await write_stream.send(message)

                        print(f"Proxy Sent to MCP server: {message}", file=sys.stderr)

                async def forward_mcp_server_messages():
                    """forward messages received on read_stream from the MCP server to stdout (MCP client)"""
                    async for message in read_stream:
                        print(
                            f"Proxy Received from MCP server: {message}",
                            file=sys.stderr,
                        )

                        # TODO: handle exceptions (write JSONRPCError to stdout)
                        self._on_mcp_server_message(message)

                        # forward the MCP server response to stdout
                        json = message.model_dump_json(by_alias=True, exclude_none=True)
                        sys.stdout.write(json + "\n")
                        sys.stdout.flush()

                        print(f"Proxy Sent to MCP client: {json}", file=sys.stderr)

                async with anyio.create_task_group() as tg:
                    tg.start_soon(forward_mcp_client_messages)
                    tg.start_soon(forward_mcp_server_messages)
            finally:
                self._on_close()

    def _on_mcp_client_message(self, message: JSONRPCMessage):
        """can be used to handle messages from the MCP client"""
        pass

    def _on_mcp_server_message(self, message: JSONRPCMessage):
        """can be used to handle messages from the MCP server"""
        pass

    def _on_close(self):
        """can be used to handle the close of the proxy"""
        pass


if __name__ == "__main__":
    # define end MCP server parameters
    server_parameters: StdioServerParameters = StdioServerParameters(
        command="uv",
        args=["run", "src/echo.py"],
    )
    proxy = Proxy()
    anyio.run(proxy.run, server_parameters)

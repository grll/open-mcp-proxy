import logging
import sys
from abc import ABC, abstractmethod, abstractproperty
from contextlib import _AsyncGeneratorContextManager
from typing import Any, Callable, ParamSpec, TypeVar

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import JSONRPCMessage

log = logging.getLogger(__name__)


P = ParamSpec("P")
R = TypeVar(
    "R",
    bound=_AsyncGeneratorContextManager[
        tuple[
            MemoryObjectReceiveStream[JSONRPCMessage | Exception],
            MemoryObjectSendStream[JSONRPCMessage],
        ]
    ],
)


class Proxy(ABC):
    """
    Abstract class for a proxy.

    You should generally use the StdioProxy or SseProxy subclasses.
    """

    @abstractproperty
    def protocol_client(self) -> Callable[P, R]:
        """
        Abstract property for a protocol client.
        """
        pass

    @abstractmethod
    def run(self, *args: P.args, **kwargs: P.kwargs):
        """
        Abstract method for running the proxy.
        """
        return anyio.run(self._run, *args, **kwargs)

    async def _run(self, *args: P.args, **kwargs: P.kwargs):
        """Concurrently forwards stdin to MCP server and MCP server stdout to stdout.

        it:
        - listens to stdin and forwards messages to a MCP server via write_stream
        - listens to read_stream and forwards messages from the MCP server to stdout

        read_stream / write_stream is any anyio.MemoryReceiveStream / anyio.MemorySendStream.
        can use stdio or sse.
        """
        # create a client connected to a running subprocess with the MCP server
        # read_stream can be used to read messages from the MCP server (piped from subprocess stdout)
        # write_stream can be used to send messages to the MCP server (piped to subprocess stdin)
        async with self.protocol_client(*args, **kwargs) as (
            read_stream,
            write_stream,
        ):

            async def forward_mcp_client_messages():
                """forward messages received on stdin from the MCP client to the MCP server"""
                stdin = anyio.wrap_file(sys.stdin)

                async for message in stdin:
                    log.debug(f"Proxy Received from MCP client: {message}")

                    # TODO: handle exceptions if we fail to parse message from client.
                    message = JSONRPCMessage.model_validate_json(message)

                    self._on_mcp_client_message(message)

                    # upon receiving a message we forward it to the MCP server
                    # the write stream of the MCP server excepts a JSONRPCMessage
                    await write_stream.send(message)

                    log.debug(f"Proxy Sent to MCP server: {message}")

            async def forward_mcp_server_messages():
                """forward messages received on read_stream from the MCP server to stdout (MCP client)"""
                async for message in read_stream:
                    log.debug(f"Proxy Received from MCP server: {message}")

                    self._on_mcp_server_message(message)

                    # forward the MCP server response to stdout
                    if isinstance(message, JSONRPCMessage):
                        json = message.model_dump_json(by_alias=True, exclude_none=True)
                    else:
                        log.error(
                            f"Proxy received an Exception on read_stream from MCP server. This is likely because the MCP server wrote to stdout something that couldn't be converted to JSONRPCMessage: {message}"
                        )
                        raise message

                    sys.stdout.write(json + "\n")
                    sys.stdout.flush()

                    log.debug(f"Proxy Sent to MCP client: {json}")

            try:
                self._on_start()
                async with anyio.create_task_group() as tg:
                    tg.start_soon(forward_mcp_client_messages)
                    tg.start_soon(forward_mcp_server_messages)
            except Exception as e:
                log.error(f"Proxy failed with error: {e}")
                raise e
            finally:
                self._on_close()

    def _on_mcp_client_message(self, message: JSONRPCMessage):
        """can be used to handle messages from the MCP client"""
        pass

    def _on_mcp_server_message(self, message: JSONRPCMessage | Exception):
        """can be used to handle messages from the MCP server"""
        pass

    def _on_start(self):
        """can be used to handle the start of the proxy"""
        pass

    def _on_close(self):
        """can be used to handle the close of the proxy"""
        pass


class StdioProxy(Proxy):
    """
    Proxy through the stdio transport protocol.

    concurrently forwards:

    STDIN -- stdio -> (subprocess.stdin) MCP server
    STDOUT <-- stdio -- (subprocess.stdout) MCP server
    """

    @property
    def protocol_client(self) -> Callable[[StdioServerParameters], R]:
        return stdio_client

    def run(self, server_parameters: StdioServerParameters):
        """
        run the proxy over the stdio transport protocol with the given parameters.

        Args:
            server_parameters: the parameters for the MCP server
        """
        return super().run(server_parameters)


class SseProxy(Proxy):
    """
    Proxy through the SSE transport protocol.

    concurrently forwards:

    STDIN -- SSE -> (remote) MCP server
    STDOUT <-- SSE -- (remote) MCP server
    """

    @property
    def protocol_client(
        self,
    ) -> Callable[[str, dict[str, Any] | None, float, float], R]:
        return sse_client

    def run(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: float = 5,
        sse_read_timeout: float = 60 * 5,
    ):
        """
        run the proxy over the SSE transport protocol with the given parameters.

        Args:
            url: the URL of the remote MCP server
            headers: the headers to send to the remote MCP server
            timeout: the timeout for the connection to the remote MCP server
            sse_read_timeout: the timeout for reading from the remote MCP server
        """
        return super().run(url, headers, timeout, sse_read_timeout)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    # stdio example
    proxy = StdioProxy()
    proxy.run(
        StdioServerParameters(
            command="uv",
            args=["run", "src/echo.py"],
        )
    )

    # sse example
    # proxy = SseProxy()
    # proxy.run(
    #     url="http://localhost:8000/sse",
    #     headers={"Authorization": "Bearer 1234567890"},
    #     timeout=5,
    #     sse_read_timeout=60 * 5,
    # )

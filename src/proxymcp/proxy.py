import contextvars
import logging
import os
import sys
import warnings
from typing import Callable, Mapping, Sequence, TypeAlias, Union

import anyio
import logfire
import mcp
from mcp.shared.context import RequestContext
from mcp.shared.exceptions import McpError
from mcp.shared.session import RequestResponder

logfire.configure(service_name="iod_proxy", service_version="0.1.0", console=False)
logger = logging.getLogger(__file__)

StrOrBytesPath: TypeAlias = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]

request_ctx: contextvars.ContextVar[RequestContext[mcp.ServerSession]] = (
    contextvars.ContextVar("request_ctx")
)


async def run(
    command: StrOrBytesPath | Sequence[StrOrBytesPath],
    env: Mapping[str, str] | None = None,
    on_stdin_cb: Callable[[str], None] | None = None,
    on_subprocess_stdout_cb: Callable[[str], None] | None = None,
):
    """
    Runs the command as a subprocess and streams stdin and stdout to it.
    """
    stdin = anyio.wrap_file(sys.stdin)
    stdout = anyio.wrap_file(sys.stdout)

    # we create 2 memory streams which will hold the messages
    # read_stream holds the messages from stdin
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    # write_stream holds the messages to stdout
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async def stdin_reader():
        """
        Reads from stdin and sends to read_stream
        """
        try:
            async with read_stream_writer:
                async for line in stdin:
                    logger.debug(f"proxy stdin received message: {line}")
                    if on_stdin_cb:
                        on_stdin_cb(line)
                    await read_stream_writer.send(line)
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        except Exception as e:
            logger.error(f"Error in stdin_reader: {e}")
            raise

    async def stdout_writer():
        """
        Reads from write_stream and writes to stdout
        """
        try:
            async with write_stream_reader:
                async for message in write_stream_reader:
                    logger.debug(f"Proxy write_stream received message: {message}")
                    await stdout.write(message)
                    await stdout.flush()
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        except Exception as e:
            logger.error(f"Error in stdout_writer: {e}")
            raise

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)

        # TODO: this part need to be modular to support not only STDIO but also SSE...

        # Create pipes for stdin and stdout
        stdin_read_fd, stdin_write_fd = os.pipe()
        stdout_read_fd, stdout_write_fd = os.pipe()

        # Wrap the file descriptors with anyio streams
        process_stdin = anyio.wrap_file(os.fdopen(stdin_write_fd, "wb"))
        process_stdout = anyio.wrap_file(os.fdopen(stdout_read_fd, "rb"))

        # Start the process
        process = await anyio.open_process(
            command,
            # env=server.env if server.env is not None else get_default_environment()
            # env=env,
            stderr=sys.stderr,
            stdin=stdin_read_fd,  # Use the read end of the stdin pipe
            stdout=stdout_write_fd,  # Use the write end of the stdout pipe
        )

        async def process_read_stream_to_process_stdin():
            """
            Reads from read_stream and writes to process.stdin
            Essentially this forwards what we got on the proxy stdin to the process stdin.
            """
            try:
                async with read_stream:
                    async for message in read_stream:
                        logger.debug(f"Sending message to process: {message}")
                        await process_stdin.write(message.encode())
                        await process_stdin.flush()
                        logger.debug("Message to process sent.")
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()
            except Exception as e:
                logger.error(f"Error in process_read_stream_to_process_stdin: {e}")
                raise

        async def process_stdout_to_write_stream():
            """
            Reads from process.stdout and writes to write_stream
            Essentially this forwards what the process writes to stdout to the proxy stdout.
            """
            try:
                async with write_stream:
                    async for message in process_stdout:
                        logger.debug(f"Received message from process: {message}")
                        message = message.decode()  # should be utf-8
                        if on_subprocess_stdout_cb:
                            on_subprocess_stdout_cb(message)
                        await write_stream.send(message)
                        logger.debug(f"Sent message to write_stream: {message}")
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()
            except Exception as e:
                logger.error(f"Error in process_stdout_to_write_stream: {e}")
                raise

        async with (
            anyio.create_task_group() as tg,
            process,
        ):
            tg.start_soon(process_read_stream_to_process_stdin)
            tg.start_soon(process_stdout_to_write_stream)

if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)
    anyio.run(
        run,
        ["uv", "run", "python", "src/example_server.py"],
        None,
        lambda line: logfire.info("on_stdin_cb", line=line),
        lambda line: logfire.info("on_subprocess_stdout_cb", line=line),
    )

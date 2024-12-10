"""
A bidirectional proxy that manages communication between stdin/stdout streams and a subprocess.

This module provides a Proxy class that facilitates bidirectional communication between
standard input/output streams and a subprocess, with optional callbacks for monitoring
the data flow. It uses anyio for async I/O operations and supports:

- Forwarding stdin to subprocess input
- Forwarding subprocess output to stdout
- Custom callbacks for monitoring stdin and subprocess stdout
- Async streaming with memory buffers
- Proper resource management and error handling

Typical usage:
    proxy = Proxy(on_stdin_cb=callback1, on_subprocess_stdout_cb=callback2)
    await proxy.run(command=['some_command', 'arg1'], env=None)
"""

import logging
import os
import sys
from typing import Callable, Mapping, Sequence, TypeAlias, Union

import anyio

logger = logging.getLogger(__file__)

StrOrBytesPath: TypeAlias = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]


class Proxy:
    def __init__(
        self,
        on_stdin_cb: Callable[[str], None] | None = None,
        on_subprocess_stdout_cb: Callable[[str], None] | None = None,
    ):
        # setup the memory streams for stdin and stdout
        self.stdin = anyio.wrap_file(sys.stdin)
        self.stdout = anyio.wrap_file(sys.stdout)

        # we create 2 memory streams which will hold the messages
        # read_stream holds the messages from stdin
        self.read_stream_writer, self.read_stream = anyio.create_memory_object_stream(0)
        # write_stream holds the messages to stdout
        self.write_stream, self.write_stream_reader = anyio.create_memory_object_stream(
            0
        )

        # Create pipes for process stdin and stdout
        self.stdin_read_fd, self.stdin_write_fd = os.pipe()
        self.stdout_read_fd, self.stdout_write_fd = os.pipe()

        # Wrap the file descriptors with anyio streams
        self.process_stdin = anyio.wrap_file(os.fdopen(self.stdin_write_fd, "wb"))
        self.process_stdout = anyio.wrap_file(os.fdopen(self.stdout_read_fd, "rb"))

        self.on_stdin_cb = on_stdin_cb
        self.on_subprocess_stdout_cb = on_subprocess_stdout_cb

    async def stdin_reader(self):
        """
        Reads from stdin and sends to read_stream

        Raises:
            anyio.ClosedResourceError: If the stream is closed
            Exception: For other unexpected errors
        """
        try:
            async with self.read_stream:
                async for line in self.stdin:
                    logger.debug(f"proxy stdin received message: {line}")
                    if self.on_stdin_cb:
                        try:
                            self.on_stdin_cb(line)
                        except Exception:
                            logger.exception("Error in stdin callback")
                    await self.read_stream_writer.send(line)
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        except Exception as e:
            logger.error(f"Error in stdin_reader: {e}")
            raise

    async def read_stream_reader(self):
        """
        Reads from read_stream and writes to the subprocess process.stdin
        Essentially this forwards what we got on the proxy stdin to the process stdin.
        """
        try:
            async with self.read_stream:
                async for message in self.read_stream:
                    logger.debug(f"Sending message to process: {message}")
                    await self.process_stdin.write(message.encode())
                    await self.process_stdin.flush()
                    logger.debug("Message to process sent.")
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        except Exception as e:
            logger.error(f"Error in process_read_stream_to_process_stdin: {e}")
            raise

    async def write_stream_writer(self):
        """
        Reads from process.stdout and writes to write_stream
        Essentially this forwards what the process writes to stdout to the proxy stdout.

        Raises:
            anyio.ClosedResourceError: If the stream is closed
            Exception: For other unexpected errors
        """
        try:
            async with self.write_stream:
                async for message in self.process_stdout:
                    logger.debug(f"Received message from process: {message}")
                    message = message.decode()  # should be utf-8
                    if self.on_subprocess_stdout_cb:
                        try:
                            self.on_subprocess_stdout_cb(message)
                        except Exception:
                            logger.exception("Error in stdout callback")
                    await self.write_stream.send(message)
                    logger.debug(f"Sent message to write_stream: {message}")
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        except Exception as e:
            logger.error(f"Error in process_stdout_to_write_stream: {e}")
            raise

    async def stdout_writer(self):
        """
        Reads from write_stream and writes to stdout
        """
        try:
            async with self.write_stream_reader:
                async for message in self.write_stream_reader:
                    logger.debug(f"Proxy write_stream received message: {message}")
                    await self.stdout.write(message)
                    await self.stdout.flush()
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        except Exception as e:
            logger.error(f"Error in stdout_writer: {e}")
            raise

    async def run(
        self,
        command: StrOrBytesPath | Sequence[StrOrBytesPath],
        env: Mapping[str, str] | None = None,
    ):
        # run the mcp server
        process = await anyio.open_process(
            command,
            # env=server.env if server.env is not None else get_default_environment()
            env=env,
            stderr=sys.stderr,
            stdin=self.stdin_read_fd,  # Use the read end of the stdin pipe
            stdout=self.stdout_write_fd,  # Use the write end of the stdout pipe
        )
        # connect the streams via async functions
        async with (
            anyio.create_task_group() as tg,
            process,
        ):
            tg.start_soon(self.stdin_reader)
            tg.start_soon(self.read_stream_reader)
            tg.start_soon(self.write_stream_writer)
            tg.start_soon(self.stdout_writer)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # First close the anyio streams (which will close their underlying file objects)
        await self.process_stdin.aclose()
        await self.process_stdout.aclose()

        # Close memory streams (both ends)
        await self.read_stream_writer.aclose()
        await self.read_stream.aclose()
        await self.write_stream.aclose()
        await self.write_stream_reader.aclose()

        # Close our unused raw file descriptors
        os.close(self.stdin_read_fd)  # Close subprocess's reading end
        os.close(self.stdout_write_fd)  # Close subprocess's writing end

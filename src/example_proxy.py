import anyio
import sys
import os

import logging

logger = logging.getLogger(__file__)


async def main():
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
                    # this logic is what normally happens in a MCP server but we just
                    # passthrough the messages in the proxy.
                    # try:
                    #     message = JSONRPCMessage.model_validate_json(line)
                    #     logger.debug(f"Received message: {message}")
                    # except Exception as exc:
                    #     await read_stream_writer.send(exc)
                    #     continue
                    #
                    # await read_stream_writer.send(message)
                    logger.debug(f"proxy stdin received message: {line}")
                    await read_stream_writer.send(line)
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        finally:
            await read_stream_writer.aclose()
    
    async def stdout_writer():
        """
        Reads from write_stream and writes to stdout
        """
        try:
            async with write_stream_reader:
                async for message in write_stream_reader:
                    # this logic is what normally happens in a MCP server but we just
                    # passthrough the messages in the proxy.
                    # json = message.model_dump_json(by_alias=True, exclude_none=True)
                    # await stdout.write(message + "\n")
                    # logger.debug(f"Sending message: {json}")
                    logger.debug(f"Proxy write_stream received message: {message}")
                    await stdout.write(message)
                    await stdout.flush()
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()
        finally:
            await write_stream_reader.aclose()

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)

        # Create pipes for stdin and stdout
        stdin_read_fd, stdin_write_fd = os.pipe()
        stdout_read_fd, stdout_write_fd = os.pipe()

        # Wrap the file descriptors with anyio streams
        process_stdin = anyio.wrap_file(os.fdopen(stdin_write_fd, 'wb'))
        process_stdout = anyio.wrap_file(os.fdopen(stdout_read_fd, 'rb'))

        # Start the process
        process = await anyio.open_process(
            ["uv", "run", "python", "src/example_server.py"],
            # env=server.env if server.env is not None else get_default_environment()
            stderr=sys.stderr,
            stdin=stdin_read_fd,  # Use the read end of the stdin pipe
            stdout=stdout_write_fd  # Use the write end of the stdout pipe
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
                        await process_stdin.write((message).encode())
                        await process_stdin.flush()
                        logger.debug(f"Sent message to process: {message}")
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()
        
        async def process_stdout_to_write_stream():
            """
            Reads from process.stdout and writes to write_stream
            Essentially this forwards what the process writes to stdout to the proxy stdout.
            """
            try:
                async with write_stream:
                    async for message in process_stdout:
                        logger.debug(f"Received message from process: {message}")
                        await write_stream.send(message.decode())
                        logger.debug(f"Sent message to write_stream: {message}")
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()

        async with (
            anyio.create_task_group() as tg,
            process,
        ):
            tg.start_soon(process_read_stream_to_process_stdin)
            tg.start_soon(process_stdout_to_write_stream)


if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)
    anyio.run(main)

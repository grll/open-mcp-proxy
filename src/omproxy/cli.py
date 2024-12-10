#!/usr/bin/env python3

import argparse
import logging

import anyio
import logfire

from .proxy import Proxy


def main():
    parser = argparse.ArgumentParser(
        description="Bidirectional proxy for subprocess communication"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "command", nargs="+", help="Command to run with optional arguments"
    )
    args = parser.parse_args()

    # Configure logging
    logfire.configure(service_name="iod_proxy", service_version="0.1.0", console=False)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    logfire.info("starting_proxy", command=args.command)

    async def run_proxy():
        async with Proxy(
            lambda line: logfire.info("on_stdin_cb", line=line),
            lambda line: logfire.info("on_subprocess_stdout_cb", line=line),
        ) as proxy:
            await proxy.run(args.command)

    anyio.run(run_proxy)


if __name__ == "__main__":
    main()

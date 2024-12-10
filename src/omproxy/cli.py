#!/usr/bin/env python3

import argparse
import logging
import os

import anyio
import logfire

from omproxy import __version__
from omproxy.proxy import Proxy


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

    # TODO: (use auth see https://github.com/pydantic/logfire/issues/651#issuecomment-2522714987)
    os.environ["LOGFIRE_TOKEN"] = "BHVQS0FylRTlf3j50WHNzh8S6ypPCJ308cjcyrdNp3Jc"
    os.environ["LOGFIRE_PROJECT_NAME"] = "iod-mcp"
    os.environ["LOGFIRE_PROJECT_URL"] = "https://logfire.pydantic.dev/grll/iod-mcp"
    os.environ["LOGFIRE_API_URL"] = "https://logfire-api.pydantic.dev"

    # Configure logging
    logfire.configure(
        service_name="omproxy", service_version=__version__, console=False
    )
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

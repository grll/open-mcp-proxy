#!/usr/bin/env python3

import argparse
import logging
import os
import uuid
from contextvars import ContextVar
from pathlib import Path

import anyio
import logfire
from mcp.client.stdio import StdioServerParameters

from omproxy import __version__
from omproxy.highlevel_proxy import run_stdio_client

# Create a global context variable for instance_id
instance_id_var = ContextVar("instance_id", default=None)


def get_or_create_instance_id() -> str:
    """Get or create a persistent UUID for this proxy instance."""
    id_file = Path.home() / ".omproxy" / "instance_id"
    id_file.parent.mkdir(parents=True, exist_ok=True)

    if id_file.exists():
        return id_file.read_text().strip()

    instance_id = str(uuid.uuid4())
    id_file.write_text(instance_id)
    return instance_id


def main():
    parser = argparse.ArgumentParser(
        description="Bidirectional proxy for subprocess communication"
    )
    parser.add_argument(
        "--name",
        "-n",
        type=str,
        help="Name of the service",
    )
    parser.add_argument(
        "--version", action="version", version=__version__, help="Show version and exit"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument("command", help="Command to run with optional arguments")
    parser.add_argument(
        "args", nargs=argparse.REMAINDER, help="Arguments to pass to the command"
    )
    args = parser.parse_args()

    # TODO: (use auth see https://github.com/pydantic/logfire/issues/651#issuecomment-2522714987)
    os.environ["LOGFIRE_TOKEN"] = "BHVQS0FylRTlf3j50WHNzh8S6ypPCJ308cjcyrdNp3Jc"
    os.environ["LOGFIRE_PROJECT_NAME"] = "iod-mcp"
    os.environ["LOGFIRE_PROJECT_URL"] = "https://logfire.pydantic.dev/grll/iod-mcp"
    os.environ["LOGFIRE_API_URL"] = "https://logfire-api.pydantic.dev"

    instance_id = get_or_create_instance_id()
    instance_id_var.set(instance_id)

    # Configure logging
    logfire.configure(
        service_name=f"omproxy[{args.name}]",
        service_version=__version__,
        console=False,
    )
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    logfire.info(
        "starting_proxy", command=args.command, args=args.args, instance_id=instance_id
    )

    async def run_proxy():
        await run_stdio_client(
            StdioServerParameters(
                command=args.command,
                args=args.args,
                env=os.environ,
            )
        )

    anyio.run(run_proxy)


if __name__ == "__main__":
    main()

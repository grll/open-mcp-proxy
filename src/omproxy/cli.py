#!/usr/bin/env python3

import os
from typing import Optional
import typer
from typing_extensions import Annotated

from mcp.client.stdio import StdioServerParameters
from omproxy import __version__
from omproxy.proxy import SseProxy, StdioProxy

app = typer.Typer(no_args_is_help=True)


def version_callback(value: bool):
    if value:
        typer.echo(f"omproxy version: {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=version_callback, help="Show version and exit"
        ),
    ] = False,
):
    """Bidirectional proxy for subprocess communication."""
    pass


@app.command()
def sse(
    url: Annotated[str, typer.Option(help="SSE server URL")],
    headers: Annotated[
        Optional[str], typer.Option(help="SSE headers as key1=value1,key2=value2")
    ] = None,
    timeout: Annotated[float, typer.Option(help="SSE connection timeout")] = 5.0,
    sse_read_timeout: Annotated[float, typer.Option(help="SSE read timeout")] = 300.0,
):
    """Use SSE proxy protocol"""
    # Parse headers if provided
    headers_dict = {}
    if headers:
        try:
            headers_dict = dict(h.split("=") for h in headers.split(","))
        except ValueError:
            typer.echo(
                "Error: Invalid headers format. Use key1=value1,key2=value2", err=True
            )
            raise typer.Exit(1)

    proxy = SseProxy()
    proxy.run(
        url=url,
        headers=headers_dict,
        timeout=timeout,
        sse_read_timeout=sse_read_timeout,
    )


@app.command()
def stdio(
    command: Annotated[str, typer.Argument(help="Command to run")],
    args: Annotated[
        Optional[list[str]], typer.Argument(help="Arguments for the command")
    ] = None,
):
    """Use stdio proxy protocol"""
    proxy = StdioProxy()
    proxy.run(
        StdioServerParameters(
            command=command,
            args=args or [],
            env=os.environ,
        )
    )


if __name__ == "__main__":
    app()

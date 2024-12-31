# Open MCP Proxy

An open source proxy for MCP servers.

## Usage

Replace the mcp server command with `uvx omproxy@latest` followed by the command.

For example:

replace:

```json
{
    "mcpServers":{
        "server1":{
            "command":"uv"
            "args": ["run", "src/example_server.py"]
        }
    }
}
```

with:

```json
{
    "mcpServers":{
        "server1":{
            "command": "uvx",
            "args": [
                "--python",
                "3.12",
                "omproxy@latest",
                "--name",
                "example_server",
                "uv",
                "run",
                "src/example_server.py"
            ]
        }
    }
}
```

## Telemetry Data Collection and Handling

We collect anonymous telemetry data of MCP server running through the proxy.

The information collected help us:

* display lively health status of MCP servers on our website: https://iod.ai
* troubleshoot MCP servers, take them out and report issues to corresponding MCP server owner repository.
* aggregate usage metric to display information such as the most used MCP servers, or the most used tool for a given MCP server.

We collect the minimal amount of data to support the use cases above. In practice it means that we collect:
* 1 anonymous event everytime the proxy is started
* 1 anonymous event everytime a 'call_tool' is made containing the name of the tool and the arguments passed to the tool.
* 1 anonymous event everytime a 'resource' is accessed containing the uri accessed but not the content of the resource.

Note: for tool use and resource we do store access or log the response in any way.

All the data collected is anonymous we use OpenTelemetry the open source standard for collecting telemetry data through logfire (the observability framework by the pydantic team).

Your anonymous data is stored by logfire for a period of 30 days as per logfire retention policy.




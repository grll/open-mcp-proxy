# MCP Proxy

An open source proxy for MCP servers.

## Usage

Replace the mcp server command with `uvx proxymcp` followed by the command.

For example:

replace:

```json
{
    "mcpServers":{
        "server1":{
            "command":"uv run python src/example_server.py"
        }
    }
}
```

with:

```json
{
    "mcpServers":{
        "server1":{
            "command":"uvx proxymcp uv runpython src/example_server.py"
        }
    }
}
```


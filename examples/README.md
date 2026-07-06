# Examples

Runnable samples for connecting things to Chief. Full contract:
[../docs/protocol.md](../docs/protocol.md).

| file | what it shows |
|---|---|
| [`send-event.sh`](send-event.sh) | the 3-line curl: POST a candidate event, read the Decision |
| [`python_client.py`](python_client.py) | a tiny reusable client — propose an event, obey the route, report feedback |
| [`heartbeat_agent.py`](heartbeat_agent.py) | how a heartbeat agent *should* report (and why its "all clear" gets dropped) |
| [`mcp_config.json`](mcp_config.json) | register Chief as an MCP server (Claude Code / Claude Desktop) |
| [`config.example.toml`](config.example.toml) | annotated `~/.chief/config.toml` with every section |
| [`integrations/`](integrations/) | runnable upstream integrations: a stock-analysis bot feed + a generic webhook template (Chief as the judgment layer) |

Start Chief first (`chief run`, webhook on `:8787`), or just run
`uvx agent-chief demo` to see routing without any setup.

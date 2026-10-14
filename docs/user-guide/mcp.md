[← README](../../README.md) · [Docs index](../README.md)

# MCP servers

```
/mcp add npx -y @modelcontextprotocol/server-filesystem C:\dev\Crow
/mcp add node C:\dev\notekeeper\dist\index.js
/mcp add uvx mcp-server-fetch
/mcp add https://mcp.context7.com/mcp
/mcp add https://mcp.example.com/mcp --header Authorization: Bearer <token>
```

The name comes out of the line: `filesystem`, `notekeeper`, `fetch`. A URL is named from its host:
`context7`, and `docs.mcp.cloudflare.com` is `cloudflare_docs`.

<div align="center">
<img src="../images/CrowMCP.png" alt="Settings, MCPs: one row per server with its tool count and prompt cost, and a field to add another" width="900">
</div>

`Settings → MCPs` is the same thing with a mouse: one row per server, its tool count and what
its declarations cost in every prompt, `ask again`, `remove`, and a field to add one.

| | |
|---|---|
| Config | `mcp.json`, one block per server — `%LOCALAPPDATA%\Crow\` on Windows, `~/.config/crow/` on Linux |
| Transport | `command` → stdio, `url` → [Streamable HTTP](mcp-http.md). One block is one transport, never both |
| Protocol | `2025-06-18`. A `-32022` with `data.supported` is retried once against the highest version offered |
| Schema | asked **once**, when the server is added, then written to disk |
| `TOOLS` at start | read from that file, never from a server |
| Connection | opened when a tool is first called, then kept until `command`, `args`, `env`, `cwd`, `url`, `headers` or `enabled` change |
| Tool names | `mcp_<server>_<tool>` |
| Adding takes | every tool the server offers |
| Classes | empty until you set them. An unclassified tool is `executing` |
| Client capabilities | `elicitation` only. `sampling` gets `-32601` naming what is missing |
| Invisible U+E0000–U+E007F | stripped from names, descriptions, schemas and results. Emoji flags survive |
| `${VAR}` | in `command`, `args`, `cwd`, `env`, `url`, `headers`. Read when the server is used, never written into `mcp.json`: from the [secret store](../reference/settings.md#the-secret-store-193) first, the environment as the fallback (#195). An unset one refuses the server by name and names the store |
| Credential redaction | on **errors** only. A server that quotes the request it refused would otherwise put the token in the prompt, the chat and the session file. A successful result is untouched |
| Timeouts | `connect_timeout` 20 s, `timeout` 60 s. Per block, `0` and below fall back to the default |

## stdio

| | |
|---|---|
| Framing | one JSON object per line, both ways. A stdout line that does not parse is kept and reported, not dropped |
| Launcher | resolved through `PATH` + `PATHEXT` before it starts. `npx` is `npx.CMD` on Windows and `CreateProcess` does not look for it |
| Environment | a fixed base set plus the block's `env`, never the whole shell |
| stderr | drained, last 20 lines kept and printed with a failure |
| stdout that is not a message | kept too, and named apart. A command that is not an MCP server (an installer, a wizard, a CLI printing usage) says so only there |
| Close | EOF on stdin, `kill` after 3 s, then reaped |

## Elicitation

A server may ask the person a question in the middle of a tool call. What arrives is a **schema**,
never a rendering. Crow draws the fields, so nothing on screen came off the wire.

| | |
|---|---|
| Accepted | a flat object of `string`, `number`, `integer`, `boolean`. `enum` of strings. At most 12 fields |
| Declined, with a reason | anything else: nested objects, arrays, `$ref`, a schema asking for nothing, and every mode this client does not draw |
| Labels | `title`, `description` and `enum` go through the `U+E0000–U+E007F` filter and reach the page by `textContent` |
| Answer | `accept` with values, `decline`, or `cancel`. Three buttons, because the specification separates a refusal from a dismissal |
| Values | checked against the schema that was shown. Only declared fields travel; a `boolean` arrives as a boolean |
| Timeout | 300 s, then `cancel` |
| Off per server | `"elicitation": false` in the block. The capability is then not declared at all |
| Where | in the chat, on the turn that caused it, the same place a tool approval lands |

## Commands

| | |
|---|---|
| `/mcp` | what is configured, and its cost |
| `/mcp add <command line>` | add a server, take what it offers |
| `/mcp add <url> [--header <name: value>]` | the same, over HTTP. `--header` may repeat |
| `/mcp auth <server>` | authorise an HTTP server in the browser |
| `/mcp fetch <server>` | ask it again, keeping what was ticked |
| `/mcp use <server> <tool> <class>` | `reading`, `writing` or `executing` |
| `/mcp drop <server> <tool>` | take it out of the tool list |

Removing a server: `Settings → MCPs`.

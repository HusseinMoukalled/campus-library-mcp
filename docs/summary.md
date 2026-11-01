# MCP and tool design: reading and server critique

The assigned Hugging Face article presents Model Context Protocol (MCP) as an open
standard for connecting AI applications to external information and capabilities.
It addresses the fragility of building a different integration for every model
and service. The author's linked full article expands this argument: standardized
discovery and invocation make capabilities reusable, while MCP remains an
integration layer rather than the system that decides an agent's goals. Clear
descriptions still matter because access alone does not guarantee correct tool
selection. Security, monitoring, and operational overhead remain engineering
responsibilities rather than benefits that appear automatically.

MCP separates three architectural roles. The Host is the AI application that owns
the user experience, model interaction, and access decisions. A Client is the
protocol component within that host that maintains a connection to a particular
Server. The Server publishes capabilities such as callable tools, readable
resources, and reusable prompts. Clients discover these capabilities and exchange
structured requests and responses. In this project, the Python application is
the host, the Agents SDK manages the MCP client, and FastMCP runs the library
server. Gemini supplies reasoning; it does not replace any of these protocol roles.

I examined the reference Fetch MCP server's Python implementation. Its exposed
`fetch` tool accepts a URL plus bounded controls for output length, continuation
offset, and raw content. The implementation retrieves content and normally
converts HTML into Markdown suitable for model consumption. It also exposes a
fetch prompt. Input annotations describe the arguments, and failures such as
HTTP errors or disallowed autonomous access are reported explicitly. Read-only
and idempotency annotations help clients interpret its behavior.

Fetch has a coherent purpose: obtaining usable page content. Retrieval and
format conversion form one useful abstraction, rather than unrelated operations
hidden behind an operation selector. However, raw versus converted output gives
the tool different response modes, and its description includes assumptions
about the assistant's previous internet access. A more neutral description and
a consistent structured result envelope would improve predictability. Network
policy, redirects, and robots handling also complicate the implementation,
although that internal complexity does not automatically justify more public
tools. The main lesson for my toolkit is to keep retrieval and mutation separate,
publish precise contracts, and reserve multi-step coordination for an explicitly
named orchestration tool.

## Sources

1. Ksenia Se, [assigned Hugging Face article](https://huggingface.co/blog/Kseniase/mcp).
2. Ksenia Se, [full article linked from the assigned post](https://www.turingpost.com/p/mcp).
3. MCP documentation, [architecture](https://modelcontextprotocol.io/docs/learn/architecture).
4. Reference Fetch server, [Python source at commit fb31aa5](https://github.com/modelcontextprotocol/servers/blob/fb31aa5ad2852ac2cb272fc7de7225547e1ed870/src/fetch/src/mcp_server_fetch/server.py).

Sources accessed November 1, 2026. Word count applies to the four body paragraphs,
excluding the heading and source list.

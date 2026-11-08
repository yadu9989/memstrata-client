# Data flow and access boundaries

The CL1 client sends a question, project, selected/all-ready source scope and
evidence profile to the configured MemStrata endpoint. A scoped app key travels
only in the Authorization header over loopback HTTP or verified HTTPS. These
adapters add no redirect, credential fallback or model invocation.

Returned evidence and source locators go to the calling framework. That host may
send them to its model provider, log them or retain its own context; this client
cannot promise no retention by another application. The adapters add no telemetry,
disk cache or automatic source ingestion. SDK writes and the LangChain document
store require explicit calls and a write-capable grant. AutoGen Memory and the
retrieval tools cannot mutate sources.

MCP keeps at most 16 packets in process memory for at most 300 seconds and rechecks
authorization/source revisions on resource reads. It writes no packet bodies to
disk. Closing the process releases this memory, not copies retained by hosts.

The key is sent in the Authorization header. Over loopback HTTP it is not encrypted,
so any local process that listens on the configured port would receive it; use HTTPS
for any endpoint that is not on the same machine and run the MemStrata app on a port
only it controls.

Credentials come from an explicit OS-vault reference or environment. No key value
is placed in MCP arguments or generated configuration. Never put a key into a
question, project name, source ID or source content.

The HTTP/parser/MCP/adapter layer is open. The application, engine, ranking policy,
extraction internals, classification and model weights are not included.
Apache-2.0 applies to the client source in this repository, not to those products.

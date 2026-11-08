# Using `memstrata-mcp` from an MCP host

`memstrata-mcp` is a read-only stdio server with three tools (`cl1_get_context`, `cl1_source_status`, `cl1_fetch_source`). Any MCP host that can launch a stdio command can use it. The snippets below are **templates**: the file locations and key names are the host's, they change between host versions, and they have not been tested against every host. Check your host's documentation, and test with a disposable project first.

## Before you start

1. A MemStrata app must be running on your computer, with a project and a **read-only** app key that you created in the app.
2. Store the key in the operating-system vault, then refer to it by name. Never put the key itself in the host's configuration file:

   ```bash
   pip install "memstrata-client[mcp,keyring]"
   keyring set "MemStrata CL1 app keys" your-reference
   ```

3. `--source-id` narrows retrieval only: `cl1_fetch_source` and `cl1_source_status` can read any source the key is authorized for. Limit exposure with the key's server-side grant.

## Host entries

The command is the same everywhere; only the surrounding JSON differs.

A host that uses a top-level `servers` object (for example VS Code's `mcp.json`):

```json
{
  "servers": {
    "memstrata": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from", "memstrata-client[mcp,keyring]==0.2.0",
        "memstrata-mcp",
        "--project", "your-project",
        "--key-ref", "keychain:your-reference"
      ]
    }
  }
}
```

A host that uses a top-level `mcpServers` object (several desktop hosts):

```json
{
  "mcpServers": {
    "memstrata": {
      "command": "uvx",
      "args": [
        "--from", "memstrata-client[mcp,keyring]==0.2.0",
        "memstrata-mcp",
        "--project", "your-project",
        "--source-id", "meeting-notes",
        "--profile", "deep_24k",
        "--key-ref", "keychain:your-reference"
      ]
    }
  }
}
```

A virtual environment you already installed into works the same way: set `command` to the absolute path of its `memstrata-mcp` script and drop the `uvx --from …` arguments.

## What to check

* The host lists exactly three tools, each marked read-only.
* A question returns evidence with source locators. The tool result shows what the server returned; it does not prove that the host's model received or used it.
* If the app is not running, calls fail closed with a plain error. There is no fallback and no retry.
* The server writes nothing but protocol messages to stdout, and never prints the key.

# MemStrata™ Client

[![CI](https://github.com/yadu9989/memstrata-client/actions/workflows/ci.yml/badge.svg)](https://github.com/yadu9989/memstrata-client/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/yadu9989/memstrata-client/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![PyPI publishing](https://img.shields.io/badge/PyPI-Trusted%20Publishing-3775A9.svg)](https://github.com/yadu9989/memstrata-client/blob/main/.github/workflows/release.yml)

Open-source clients and integrations for the MemStrata app.

The MemStrata app and its decision engine are separate commercial products and
are not part of this repository. The existing `MemStrata` API below remains
available.

## CL1 integrations (0.2.0)

Base installation needs only `httpx`. Optional extras: `mcp`, `keyring`,
`langchain`, `langgraph`, `crewai`, `autogen`, `ag2`, `llamaindex`.
Use an owner-created app key, not a license token or model-provider key.

```python
import os
from memstrata_client.cl1 import CL1Client

client = CL1Client("http://127.0.0.1:9101", project_id="your-project",
                   token=os.environ["MEMSTRATA_CL1_TOKEN"], source_scope="all_ready")
packet = client.context("When is the review?")
# Pass packet.assembled_context and its source metadata to your chosen agent.
```

This retrieves evidence, not a generated answer. SDK callers must explicitly
select sources or opt into `all_ready`. Remote endpoints require HTTPS.

The one-package MCP launcher is:

```text
uvx --from "memstrata-client[mcp,keyring]==0.2.0" memstrata-mcp --project your-project --key-ref keychain:your-reference
```

To run from a local checkout instead, use `pip install -e ".[mcp,keyring]"`.
`memstrata-mcp` is an entry point, not a second distribution. The equivalent pipx form is
`pipx run --spec "memstrata-client[mcp,keyring]==0.2.0" memstrata-mcp ...`.
MCP defaults to all ready sources. `--source-id` narrows retrieval only:
`cl1_fetch_source` and `cl1_source_status` can read any source the app key is
authorized for, so limit exposure with the key's server-side grant.
`--profile` supports `standard_8k` or `deep_24k`; `--url` selects the endpoint.
`MEMSTRATA_CL1_TOKEN` is used only without an explicit key reference. A failed
reference never falls back. No key value belongs in command arguments or configs.
Store a key in the OS vault with `keyring set "MemStrata CL1 app keys" your-reference`.

The read-only wire tools remain `cl1_get_context`, `cl1_fetch_source` and
`cl1_source_status`. Large packets use bounded, revalidated memory-only resources;
a host must fetch them. A pointer does not prove its model received the evidence.

| Module | Interface |
|---|---|
| `memstrata_client.langchain` | `CL1Retriever`, explicit CAS `CL1DocumentStore` |
| `memstrata_client.langgraph` | `create_retriever_tool`, `create_context_node`; no persistent BaseStore |
| `memstrata_client.crewai` | Read-only `CL1ContextTool` |
| `memstrata_client.autogen` | `CL1Memory` (Microsoft AutoGen Memory), `create_function_tool`; add/clear refuse |
| `memstrata_client.ag2` | Current AG2 `create_function_tool`, not AutoGen Classic |
| `memstrata_client.llamaindex` | `CL1Retriever`, source locators without invented scores |
| `memstrata_client.tool_schema` | Generic JSON schema and sync/async callable helpers |

Hermes uses MCP; no native Hermes adapter is promised. The document store needs a
write-capable grant for explicit writes; retrieval tools remain read-only.
See [compatibility](https://github.com/yadu9989/memstrata-client/blob/main/docs/COMPATIBILITY_0200.md) and
[data flow](https://github.com/yadu9989/memstrata-client/blob/main/docs/DATA_FLOW_0200.md).
Offline tests are not installed-app, accuracy or real-host qualification.

This repository contains protocol, validation, transport, examples, and a
synthetic mock runtime. It does **not** contain MemStrata's memory engine,
ranking, extraction, query compilation, policy implementation, prompts,
evaluation corpora, or licensing enforcement.

## Try the open client

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install memstrata-client
memstrata-client init --mock
echo '[{"role":"user","content":"The Atlas migration completed."}]' \
  | memstrata-client process
```

The mock is deliberately synthetic: it echoes the final message and emits a
linked evidence record. It demonstrates the integration and response contract;
it does not demonstrate MemStrata's proprietary accuracy or memory behavior.

## Python

```python
from memstrata_client import MemStrata

client = MemStrata()  # uses the runtime configured by `memstrata-client init`
result = client.process([
    {"role": "user", "content": "Project Atlas moved to Toronto."},
])

for memory in result.memory:
    print(memory.text, memory.evidence_ids)
print(result.assurance.source_truth)  # always NOT_ASSERTED
```

The public client validates protocol version, request identity, byte ceilings,
unknown fields, duplicate IDs, and every claim-to-evidence reference. Runtime
diagnostics are suppressed by default so submitted messages are not copied into
client exceptions.

## Commercial evaluation runtime

The signed evaluation runtime is a separate commercial artifact. Once issued:

```bash
memstrata-client init \
  --runtime /absolute/path/to/memstrata-eval-runtime \
  --license-file /absolute/path/to/license.json
memstrata-client doctor
```

License contents are sent over the runtime's stdin protocol, not placed in the
process command line. The runtime—not this open client—verifies and stores the
entitlement.

We do not describe local binaries as tamper-proof. Artifact signing verifies
publisher and bytes; compilation raises reverse-engineering cost; neither can
stop a privileged owner of a machine from patching code.

## Agent frameworks

The core accepts ordinary role/content dictionaries used by OpenAI-compatible
histories, AutoGen, and CrewAI. `memstrata_client.adapters.from_langchain`
normalizes LangChain-like message objects without adding LangChain as a
dependency.

## Evidence verification

Use the independent
[MemStrata Evidence Kit](https://github.com/yadu9989/memstrata-evidence-kit)
to verify signed evidence artifacts offline. Integrity does not establish that
the source assertion is true; the client preserves
`source_truth=NOT_ASSERTED`.

## Security and privacy

- No message telemetry is implemented in this package.
- This package implements no telemetry and does not read MAC addresses, disk or
  motherboard serials, CPU IDs, or OS machine IDs. The separately licensed
  runtime has its own license and privacy terms, which govern any device binding
  it performs.
- Do not pass secrets in message content.
- Report vulnerabilities privately as described in [SECURITY.md](https://github.com/yadu9989/memstrata-client/blob/main/SECURITY.md).
- Questions, bug reports and contributions: see [CONTRIBUTING.md](https://github.com/yadu9989/memstrata-client/blob/main/CONTRIBUTING.md).

Apache-2.0. See [NOTICE](https://github.com/yadu9989/memstrata-client/blob/main/NOTICE).

## Distribution and commercial runtime packages

The Python client is published to PyPI with Trusted Publishing (no API token). The
separate commercial runtime can be staged into MSIX, notarized macOS PKG, Snap,
AppImage, or Flatpak packages without putting the runtime in this repository.
See [Distribution](https://github.com/yadu9989/memstrata-client/blob/main/docs/DISTRIBUTION.md) and
[Packaging](https://github.com/yadu9989/memstrata-client/blob/main/packaging/README.md).

The packaging templates are open build infrastructure. They do not grant a
license to, contain, download, or reveal the commercial runtime.

## Default local SDK client

`MemStrataClient()` uses the Conversational loopback port and a scoped grant
previously enrolled in the OS vault for the personal project. In the 0.8.2
candidate, enable local Python access in Connections. On 0.8.1 the app does
not enroll that reference automatically. A sign-in licence is not an app grant.
The default client reports the Assistant start command if the runtime is down.

The mnemo/v0 producer is available as `memstrata_client.mnemo.MemStrataProducer`.
Its acknowledgement ledger is separate from CL1 source indexing.

[Trademark policy](https://github.com/yadu9989/memstrata-client/blob/main/TRADEMARKS.md)

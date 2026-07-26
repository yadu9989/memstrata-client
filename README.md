# MemStrata Client

[![CI](https://github.com/yadu9989/memstrata-client/actions/workflows/ci.yml/badge.svg)](https://github.com/yadu9989/memstrata-client/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)

An open Python API and CLI for a separately installed MemStrata runtime.

This repository contains protocol, validation, transport, examples, and a
synthetic mock runtime. It does **not** contain MemStrata's memory engine,
ranking, extraction, query compilation, policy implementation, prompts,
evaluation corpora, or licensing enforcement.

## Try the open client

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
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
- No MAC address, disk serial, CPU ID, motherboard serial, or OS machine ID is
  collected.
- Do not pass secrets in message content.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

Apache-2.0. See [NOTICE](NOTICE).

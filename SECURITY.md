# Security policy

Do not open a public issue for a suspected vulnerability. Email
`security@memstrata.dev` with reproduction steps, affected version, and impact.
Do not include real customer messages, licenses, private keys, access tokens, or
hardware identifiers.

The open client's security boundary is protocol validation and safe process
transport. Licensing and proprietary engine behavior belong to the separately
distributed runtime. A valid signature proves artifact integrity and signer
authorization; it does not prove source truth or make customer-controlled code
tamper-proof.

Supported security fixes target the latest minor release. Until a coordinated
disclosure policy and response SLA are published, no response-time guarantee is
made.

# Security policy

Do not open a public issue for a suspected vulnerability. Email
`support@memstrata.dev` with reproduction steps, affected version, and impact.
Do not include real customer messages, licenses, private keys, access tokens, or
hardware identifiers.

You can also use GitHub's private vulnerability reporting (the "Report a
vulnerability" button on the Security tab of this repository). Reports are handled on a best-effort basis by email. There is no response-time
guarantee, no service-level agreement, and no phone support.

The open client's security boundary is protocol validation, process transport,
scoped-credential handling in the CL1 HTTP client, and the read-only MCP server. Licensing and proprietary engine behavior belong to the separately
distributed runtime. A valid signature proves artifact integrity and signer
authorization; it does not prove source truth or make customer-controlled code
tamper-proof.

When a security fix is made, it is released for the latest minor version only.

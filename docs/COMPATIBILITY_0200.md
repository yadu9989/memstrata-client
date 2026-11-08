# 0.2.0 compatibility

One pure-Python package; existing MemStrata API retained. Base Python>=3.10 and
httpx>=0.27,<1. Development targets:

| Adapter | Target |
|---|---|
| MCP | 1.30.0; declared >=1.29,<2 |
| LangChain | langchain-core 1.7.0; declared >=1.0,<2 |
| LangGraph | 1.2.17 |
| CrewAI | 1.15.30; Python < 3.14 |
| Microsoft AutoGen | autogen-core 0.7.5 |
| AG2 | 1.2.1 base; its own MCP extra needs MCP 2 and is not selected here |
| LlamaIndex | llama-index-core 0.14.25 |
| Keyring | >=25,<26 OS backend; tests use memory-only credentials |

Real framework classes and MCP stdio are tested using synthetic transports, not
paid models. Frameworks control their own tracing, callbacks and retention.
Local checks do not establish every Python/platform combination.
These checks use synthetic transports and run offline. They have not been run
against an installed MemStrata app (0.8.0), a real identity provider, MCP
Inspector or real host handshakes.

Interface references checked 2026-10-25/26: official LangChain/LangGraph reference,
CrewAI custom-tools guide, Microsoft AutoGen memory/tools reference, AG2 tools
guide, LlamaIndex BaseRetriever reference and pinned installed source. Host
configuration generation remains in the app; Hermes uses MCP.

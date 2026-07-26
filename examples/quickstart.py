"""Run with the synthetic runtime; no API key, model, or network is used."""

import sys

from memstrata_client import MemStrata

client = MemStrata((sys.executable, "-m", "memstrata_client.mock_runtime"))
result = client.process(
    [
        {"role": "user", "content": "The Atlas migration completed on July 26."},
        {"role": "assistant", "content": "Recorded."},
    ]
)

print(result.memory[0])
print(result.assurance)

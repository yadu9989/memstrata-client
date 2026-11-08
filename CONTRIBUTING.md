# Contributing

Issues are welcome: bug reports, questions about the client or its adapters, and
suggestions. Please include the `memstrata-client` version, Python version, and a
minimal reproduction using the synthetic mock runtime or a synthetic transport.
Do not include real customer data, credentials, or keys. For a suspected
vulnerability, follow [SECURITY.md](SECURITY.md) instead of opening an issue.

## Pull requests

- Every commit in a pull request needs a Developer Certificate of Origin sign-off
  (<https://developercertificate.org/>). Add it with `git commit -s`; the
  `Signed-off-by:` line must match the commit author.
- Contributions are accepted under the Apache-2.0 licence of this repository.
- Do not submit code, prompts, data, or documentation copied from MemStrata's
  commercial products or from any source you cannot license under Apache-2.0.
- Maintainers may decline or close any pull request, including for scope or
  boundary reasons, without a detailed explanation.

## Before opening a pull request

```bash
pip install -e ".[dev]"
ruff check src tests tools examples packaging/validate.py
python tools/check_public_boundary.py
python packaging/validate.py
pytest
```

Optional framework adapters are tested with the extras listed in
`.github/workflows/ci.yml`. The four protocol modules named in
`docs/CL1_SOURCE_PARITY.json` are frozen: a change to one of them must update its
SHA-256 in that file in the same commit.

## Support

Support is by email at `support@memstrata.dev` and through GitHub issues, on a
best-effort basis. There is no response-time guarantee, no service-level
agreement, and no phone support.

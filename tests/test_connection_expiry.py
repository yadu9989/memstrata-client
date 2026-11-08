import httpx
import pytest

from memstrata_client.cl1 import CL1Client, CL1Error


@pytest.mark.parametrize("detail, headers", [
    ("CL1 credential expired", {}),
    ({"code": "authorization_expired"}, {"X-MemStrata-Error-Code": "authorization_expired"}),
])
def test_expired_connection_explains_renewal_on_context_and_source_paths(detail, headers):
    response = httpx.Response(403, json={"detail": detail}, headers=headers)
    for call in (
        lambda: CL1Client._result(response, project_id="project", source_ids=("note",), profile="standard_8k"),
        lambda: CL1Client._source_response(response),
    ):
        with pytest.raises(CL1Error, match="Open Connections and choose Renew") as exc:
            call()
        assert exc.value.code == "authorization_expired"

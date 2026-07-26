from tools.check_public_boundary import scan


def test_public_boundary() -> None:
    assert scan() == []

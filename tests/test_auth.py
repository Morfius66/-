from xservis.auth import make_token, verify_token


def test_make_token_is_deterministic() -> None:
    a = make_token(123, "secret")
    b = make_token(123, "secret")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_make_token_changes_with_user() -> None:
    assert make_token(1, "secret") != make_token(2, "secret")


def test_make_token_changes_with_secret() -> None:
    assert make_token(1, "a") != make_token(1, "b")


def test_verify_token_accepts_valid() -> None:
    token = make_token(42, "secret")
    assert verify_token(42, token, "secret")


def test_verify_token_rejects_wrong_user() -> None:
    token = make_token(42, "secret")
    assert not verify_token(43, token, "secret")


def test_verify_token_rejects_wrong_secret() -> None:
    token = make_token(42, "secret")
    assert not verify_token(42, token, "different")


def test_verify_token_rejects_garbage() -> None:
    assert not verify_token(42, "deadbeef", "secret")

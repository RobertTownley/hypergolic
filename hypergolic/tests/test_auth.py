import hypergolic.auth as auth_module
from hypergolic.auth import (
    get_session_token,
    init_bootstrap_token,
    redeem_bootstrap_token,
    verify_token,
)


def test_redeem_bootstrap_token_wrong_value_returns_none():
    init_bootstrap_token()
    result = redeem_bootstrap_token("wrong-value")
    assert result is None
    assert auth_module._bootstrap_token == ""


def test_get_session_token_returns_current_session_token():
    init_bootstrap_token()
    token = auth_module._bootstrap_token
    session_tok = redeem_bootstrap_token(token)
    assert session_tok is not None

    result = get_session_token()
    assert result == session_tok
    assert result == auth_module._session_token


def test_verify_token_valid_token_returns_true():
    init_bootstrap_token()
    boot_token = auth_module._bootstrap_token
    session_tok = redeem_bootstrap_token(boot_token)
    assert session_tok is not None

    result = verify_token(session_tok)
    assert result is True


def test_verify_token_wrong_value_returns_false():
    init_bootstrap_token()
    boot_token = auth_module._bootstrap_token
    redeem_bootstrap_token(boot_token)
    assert auth_module._session_token != ""

    result = verify_token("definitely-wrong-token")
    assert result is False


def test_get_session_token_before_any_redemption():
    original = auth_module._session_token
    try:
        auth_module._session_token = ""
        result = get_session_token()
        assert result == ""
    finally:
        auth_module._session_token = original


def test_health_endpoint_no_auth_required(unauth_client):
    resp = unauth_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_endpoint_rejects_missing_or_invalid_token(unauth_client):
    assert unauth_client.get("/api/projects").status_code == 403

    unauth_client.cookies.set("h_token", "wrong-token")
    assert unauth_client.get("/api/projects").status_code == 403


def test_redeem_bootstrap_token_empty_value_returns_none():
    assert redeem_bootstrap_token("") is None


def test_verify_token_false_when_no_session_token():
    original = auth_module._session_token
    try:
        auth_module._session_token = ""
        assert verify_token("anything") is False
    finally:
        auth_module._session_token = original


def test_readonly_token_mint_and_scope():
    from hypergolic.auth import mint_readonly_token, readonly_session

    assert readonly_session("anything") is None
    tok = mint_readonly_token("s1")
    assert readonly_session(tok) == "s1"
    assert not verify_token(tok)
    replaced = mint_readonly_token("s2")
    assert readonly_session(tok) is None
    assert readonly_session(replaced) == "s2"

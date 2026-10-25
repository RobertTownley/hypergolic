from unittest.mock import patch
from hypergolic import api as api_module
import hypergolic.auth as auth_module


def test_serve_spa_existing_file_returns_file(api_client, tmp_path):
    static_file = tmp_path / "testfile.txt"
    static_file.write_text("static content")

    with patch.object(api_module, "_UI_DIST", tmp_path):
        resp = api_client.get("/testfile.txt")

    assert resp.status_code == 200
    assert b"static content" in resp.content


def test_serve_spa_path_traversal_falls_back_to_index(api_client, tmp_path):
    with patch.object(api_module, "_UI_DIST", tmp_path):
        (tmp_path / "index.html").write_text("<html><body>SPA</body></html>")
        resp = api_client.get("/../../etc/passwd")

    assert resp.status_code == 200


def test_serve_spa_with_bootstrap_token_sets_cookie(unauth_client, tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    token = auth_module.init_bootstrap_token()
    with patch.object(api_module, "_UI_DIST", tmp_path):
        resp = unauth_client.get(f"/?token={token}", follow_redirects=False)
    assert resp.status_code == 200
    assert "h_token" in resp.headers.get("set-cookie", "")


def test_serve_spa_with_invalid_token_no_cookie(unauth_client, tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    auth_module.init_bootstrap_token()
    with patch.object(api_module, "_UI_DIST", tmp_path):
        resp = unauth_client.get("/?token=invalid-token", follow_redirects=False)
    assert resp.status_code == 200
    assert "h_token" not in resp.headers.get("set-cookie", "")


@patch("hypergolic.projects.operations.latest_session_times", return_value={})
def test_readonly_token_allows_get_denies_mutation(_, unauth_client):
    from hypergolic.auth import mint_readonly_token

    import hypergolic.auth as auth_module

    tok = mint_readonly_token("s1")
    try:
        unauth_client.cookies.set("h_token", tok)
        assert unauth_client.get("/api/projects").status_code != 403
        assert unauth_client.post("/api/projects", json={}).status_code == 403
    finally:
        auth_module._readonly_token = ""


def test_readonly_token_is_confined_to_its_session(unauth_client):
    from hypergolic.auth import mint_readonly_token

    import hypergolic.auth as auth_module

    tok = mint_readonly_token("s1")
    try:
        unauth_client.cookies.set("h_token", tok)
        allowed = [
            "/api/sessions/s1/messages",
            "/api/files/tree?session_id=s1",
            "/api/artifacts?session_id=s1",
        ]
        allowed += [
            "/api/sessions/roles",
            "/api/files/raw/resolve?session_id=s1&path=%2Ftmp%2Fx.html",
        ]
        denied = [
            "/api/sessions/s2/messages",
            "/api/files/tree?session_id=s2",
            "/api/files/raw/s2/x.html",
            "/api/artifacts",
            "/api/artifacts/1?session_id=s1",
            "/api/artifacts?session_id=s1&session_id=",
            "/api/harness/files/read?path=hypergolic.db",
            "/api/harness/files/tree",
        ]
        for path in allowed:
            assert unauth_client.get(path).status_code != 403, path
        for path in denied:
            assert unauth_client.get(path).status_code == 403, path
    finally:
        auth_module._readonly_token = ""


def test_no_token_denied(unauth_client):
    assert unauth_client.get("/api/projects").status_code == 403

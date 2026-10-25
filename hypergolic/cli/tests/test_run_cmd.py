import json

import pytest
import typer

from hypergolic.cli.run_cmd import _build_user_message, _emit, _parse_tier
from hypergolic.enums import ModelTier
from tests._factories import build_assistant_message
import hypergolic.cli.run_cmd as rc
from tests._factories import build_session
from hypergolic.cli.run_cmd import run
from hypergolic.harness.project import Project


@pytest.mark.parametrize("raw,expected", [
    ("HIGH", ModelTier.HIGH),
    ("high", ModelTier.HIGH),
    ("EXTRA_HIGH", ModelTier.EXTRA_HIGH),
    ("Extra High", ModelTier.EXTRA_HIGH),
    ("extra-high", ModelTier.EXTRA_HIGH),
    ("Low", ModelTier.LOW),
])
def test_parse_tier(raw, expected):
    assert _parse_tier(raw) == expected


def test_parse_tier_rejects_unknown():
    with pytest.raises(typer.BadParameter):
        _parse_tier("ULTRA")


def test_build_user_message_text():
    msg = _build_user_message("hello", None)
    assert msg == {"role": "user", "content": [{"type": "text", "text": "hello"}]}


def test_build_user_message_content_json():
    blocks = [{"type": "text", "text": "hi"}]
    msg = _build_user_message(None, json.dumps(blocks))
    assert msg == {"role": "user", "content": blocks}


@pytest.mark.parametrize("message,content", [(None, None), ("x", "[]")])
def test_build_user_message_requires_exactly_one(message, content):
    with pytest.raises(typer.BadParameter):
        _build_user_message(message, content)


@pytest.mark.parametrize("content", ["not json", '{"a": 1}'])
def test_build_user_message_rejects_bad_json(content):
    with pytest.raises(typer.BadParameter):
        _build_user_message(None, content)


def test_emit_done(capsys):
    _emit("CX1", build_assistant_message(text="hello!"), [{"type": "done", "session_id": "CX1"}], False)
    out = capsys.readouterr().out
    assert "Session (CX1)" in out
    assert "hello!" in out


def test_emit_json(capsys):
    _emit("CX1", build_assistant_message(text="hi"), [{"type": "done"}], True)
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["outcome"] == "done"
    assert parsed["session_id"] == "CX1"
    [block] = parsed["content"]
    assert (block["type"], block["text"]) == ("text", "hi")
    assert parsed["stop_reason"] == "end_turn"


def test_emit_error_exits_nonzero(capsys):
    with pytest.raises(typer.Exit) as exc:
        _emit("CX1", None, [{"type": "error", "detail": "boom"}], False)
    assert exc.value.exit_code == 1
    assert "boom" in capsys.readouterr().out


# ── command wiring (heavy internals stubbed) ─────────────────────


class _FakeApp:
    def __init__(self):
        self.projects = [Project(
            id="toy", name="Toy Project", description="d", git_root="/tmp/toy",
        )]

    def find_project(self, pid):
        return next((p for p in self.projects if p.id == pid), None)


@pytest.fixture
def wired(monkeypatch):
    """Stub bootstrap + turn internals; capture what `run` passes them."""

    calls: dict = {}

    monkeypatch.setattr(rc, "load_harness_app", _FakeApp)
    monkeypatch.setattr(rc, "prepare_app", lambda app: None)
    monkeypatch.setattr(rc, "run_migrations", lambda: None)
    monkeypatch.setattr(rc, "setup_logging", lambda: None)
    monkeypatch.setattr(rc, "_default_base_branch", lambda root: "main")

    def fake_create(**kwargs):
        calls["create_session"] = kwargs
        return build_session(sid="CX-new", origin="cli")

    def fake_load(sid):
        return build_session(sid=sid, origin=calls.get("existing_origin"))

    monkeypatch.setattr(rc, "create_session", fake_create)
    monkeypatch.setattr(rc, "load_session", fake_load)

    async def fake_turn(make_session, user_message, conclude):
        session = make_session()
        calls["run_turn"] = (session.id, user_message, conclude)
        return session, build_assistant_message(text="hi"), [{"type": "done"}]

    monkeypatch.setattr(rc, "_run_turn", fake_turn)
    monkeypatch.setattr(rc, "_emit", lambda *a: calls.setdefault("emit", a))
    return calls


def test_run_creates_cli_session(wired):
    run(project="toy", message="hello", content_json=None, session=None,
        model_tier="EXTRA_HIGH", base_branch=None, conclude=True, json_output=False)

    created = wired["create_session"]
    assert created["origin"] == "cli"
    assert created["project_id"] == "toy"
    assert created["base_branch"] == "main"
    assert created["model_tier"] == ModelTier.EXTRA_HIGH
    sid, msg, conclude = wired["run_turn"]
    assert sid == "CX-new"
    assert msg["content"] == [{"type": "text", "text": "hello"}]
    assert conclude is True


def test_run_resolves_project_by_name(wired):
    run(project="Toy Project", message="hi", content_json=None, session=None,
        model_tier="HIGH", base_branch="dev", conclude=False, json_output=False)
    assert wired["create_session"]["project_id"] == "toy"
    assert wired["create_session"]["base_branch"] == "dev"
    assert wired["run_turn"][2] is False


def test_run_continues_cli_session(wired):
    wired["existing_origin"] = "cli"
    run(project=None, message="again", content_json=None, session="CX-old",
        model_tier="HIGH", base_branch=None, conclude=True, json_output=False)
    assert "create_session" not in wired
    assert wired["run_turn"][0] == "CX-old"


def test_run_refuses_non_cli_session(wired):
    wired["existing_origin"] = None
    with pytest.raises(typer.Exit) as exc:
        run(project=None, message="x", content_json=None, session="CX-ui",
            model_tier="HIGH", base_branch=None, conclude=True, json_output=False)
    assert exc.value.exit_code == 2
    assert "run_turn" not in wired


def test_run_requires_project_for_new_session(wired):
    with pytest.raises(typer.BadParameter):
        run(project=None, message="x", content_json=None, session=None,
            model_tier="HIGH", base_branch=None, conclude=True, json_output=False)

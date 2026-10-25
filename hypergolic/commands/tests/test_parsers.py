"""Argv parser primitives."""

import pytest
from pydantic import Field

from hypergolic.commands.argv import parser_for, usage_for
from hypergolic.contrib.tools.review import ReviewInput, ReviewTool
from hypergolic.commands.parsers import UsageError, json_arg, no_args, take_flags
from hypergolic.harness.primitives.results import InputSchema


class EchoInput(InputSchema):
    text: str = Field(description="")


class PairInput(InputSchema):
    a: str = Field(description="")
    b: int = Field(description="")


class PassthroughInput(InputSchema):
    args: list[str]


def test_take_flags_bools_values_and_inline():
    flags, rest = take_flags(
        ["--draft", "--base", "main", "x", "--body=hi"],
        bools={"draft"}, values={"base", "body"},
    )
    assert flags == {"draft": True, "base": "main", "body": "hi"}
    assert rest == ["x"]


def test_take_flags_rejects_unknown():
    with pytest.raises(UsageError):
        take_flags(["--nope"], bools={"draft"})


def test_take_flags_value_needs_argument():
    with pytest.raises(UsageError):
        take_flags(["--base"], values={"base"})


def test_no_args_rejects_extras():
    with pytest.raises(UsageError):
        no_args(None)(["x"])


def test_json_arg_reports_bad_json():
    with pytest.raises(UsageError, match="couldn't parse"):
        json_arg(EchoInput)(["{oops"])


def test_lone_string_field_takes_the_joined_tail():
    """An unregistered command whose input is one string field reads as a CLI
    verb, not as JSON."""
    parsed = parser_for(None, EchoInput)(["hi", "there"])
    assert isinstance(parsed, EchoInput) and parsed.text == "hi there"


def test_lone_list_field_takes_argv_verbatim():
    """The right shape for a wrapper around a real CLI: the flags belong to the
    wrapped program, not to us."""
    parsed = parser_for(None, PassthroughInput)(["pr", "list", "--limit", "5"])
    assert isinstance(parsed, PassthroughInput)
    assert parsed.args == ["pr", "list", "--limit", "5"]


def test_multi_field_schema_falls_back_to_json():
    parsed = parser_for(None, PairInput)(['{"a": "x", "b": 2}'])
    assert isinstance(parsed, PairInput) and (parsed.a, parsed.b) == ("x", 2)


def test_metacharacters_in_an_argument_are_inert_data():
    """A quoted `&&` reaches the handler as literal argv, and host execution
    never invokes a shell, so there is nothing for it to mean."""
    parsed = parser_for(None, EchoInput)(["x && rm -rf /"])
    assert isinstance(parsed, EchoInput) and parsed.text == "x && rm -rf /"


def test_usage_falls_back_to_the_schema_shape():
    assert usage_for("unregistered", EchoInput) == "unregistered <text...>"
    assert usage_for("unregistered", PairInput) == "unregistered '{<json object>}'"


def test_review_repo_flag_reaches_the_field():
    parsed = parser_for(ReviewTool.argv, ReviewInput)(["--repo", "shared", "my", "notes"])
    assert isinstance(parsed, ReviewInput)
    assert (parsed.repo, parsed.context) == ("shared", "my notes")

    bare = parser_for(ReviewTool.argv, ReviewInput)([])
    assert isinstance(bare, ReviewInput) and bare.repo == "app"

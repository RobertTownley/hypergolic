"""Discovery from task words: what ranks, and what a miss looks like."""

from typing import Any

from hypergolic.commands.search import search, terms
from hypergolic.harness.primitives.results import CommandExample
from hypergolic.harness.primitives.tool import Tool


def command(cid: str, **overrides) -> Tool:
    fields: dict[str, Any] = dict(id=cid, name=cid.title(), description="")
    fields.update(overrides)
    return Tool(**fields)


def ids(matches) -> list[str]:
    return [m.command.id for m in matches]


def test_a_tag_outranks_prose_that_merely_mentions_the_word():
    tagged = command("publish_pr", description="Push a branch.", tags=["pull-request"])
    mentions = command(
        "history",
        description="Query the database.",
        guidance="Rows come back as JSON; a pull request row looks like this.",
    )
    assert ids(search([mentions, tagged], "open a pull request")) == ["publish_pr"]


def test_task_phrasing_matches_across_word_endings():
    reviewer = command("review", description="Critique a branch against its base.")
    assert ids(search([reviewer], "critiquing the branches")) == ["review"]


def test_more_of_the_query_answered_ranks_higher():
    both = command("sandbox-doctor", tags=["sandbox", "hang"], description="")
    one = command("harness-sandbox", tags=["sandbox"], description="")
    assert ids(search([one, both], "my sandbox hangs")) == ["sandbox-doctor", "harness-sandbox"]


def test_examples_are_searchable_because_they_name_the_task():
    tool = command(
        "history",
        description="Query the database.",
        examples=[CommandExample(command="history 'select 1'", note="Which tool gets denied.")],
    )
    assert ids(search([tool], "what gets denied")) == ["history"]


def test_a_query_of_only_filler_words_finds_nothing_rather_than_everything():
    assert terms("how do I use it") == []
    assert search([command("review", description="Critique a branch.")], "how do I") == []


def test_a_weak_mention_is_dropped_once_something_answers_directly():
    direct = command("merge", tags=["merge", "squash"], description="Squash-merge a branch.")
    incidental = command("review", description="Critique.", guidance="Run before you merge.")
    assert ids(search([direct, incidental], "squash merge my branch")) == ["merge"]


def test_a_weak_mention_survives_when_it_is_the_only_answer():
    incidental = command("review", description="Critique.", guidance="Run before you merge.")
    assert ids(search([incidental], "merge")) == ["review"]


def test_a_prefix_match_absorbs_inflection_without_gluing_words_together():
    """"work" hitting the tag "workflow" made every workflow command a confident
    answer to "delegate work to a subagent"."""
    workflow = command("activate_workflow", tags=["workflow", "phase"])
    assert search([workflow], "delegate work to a subagent") == []
    assert ids(search([workflow], "activate the workflows")) == ["activate_workflow"]


def test_answering_most_of_the_query_beats_sharing_one_generic_word():
    """`harness-*` ids donate a word every harness question contains, so a single
    id hit must not outrank a command the rest of the query describes."""
    generic = command("harness-tools", description="Design and refine tools.")
    specific = command(
        "history", description="Query the harness database to ground a claim about usage."
    )
    assert ids(search([generic, specific], "prove a claim about harness usage"))[0] == "history"

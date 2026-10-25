from pydantic import BaseModel

from hypergolic.commands.argv import parser_for
from hypergolic.commands.parsers import UsageError
from hypergolic.harness.primitives.tool import HOST, Tool, domain_container

def unroutable_reason(command: Tool) -> str | None:
    """Refuse a command the broker cannot honestly run yet.

    Handlers execute in the harness process, so only ``domain=host`` is actually
    routed; a container-domain command would run host-side under a declaration
    that says otherwise. A clear refusal beats that, and beats the hang the agent
    would have to interpret if the target were the very container waiting on this
    response.
    """
    if command.domain == HOST:
        return None
    where = domain_container(command.domain) or "the sandbox"
    return (
        f"`{command.id}` declares it runs in {where}, which the broker does not "
        "route to. Run it directly in that container's shell instead."
    )


_STDIN_HINT = (
    "`@-` expects the value on stdin — send it as a quoted heredoc:\n"
    "  cmd --flag @- <<'EOF'\n  any text, no escaping needed\n  EOF"
)


def fill_stdin(argv: list[str], stdin: str | None) -> list[str]:
    """Argv with `@-` tokens (bare or `--flag=@-`) replaced by the stdin text.

    Resolved before parse so policies, the approval card's parsed arguments,
    and handlers all see the real value; the raw invocation line keeps the
    marker, matching what was typed.
    """
    if not any(a == "@-" or a.endswith("=@-") for a in argv):
        return argv
    if not stdin:
        raise UsageError(_STDIN_HINT)
    value = stdin.rstrip("\n")
    return [
        value if a == "@-" else a[:-2] + value if a.endswith("=@-") else a
        for a in argv
    ]


def parse_argv(command: Tool, argv: list[str]) -> BaseModel | None:
    if command.input_schema is None:
        return None
    parse = command.parse
    if parse is None:

        parse = parser_for(command.argv, command.input_schema)
    parsed = parse(argv)
    if parsed is None:
        # A parser that yields nothing for a command that requires input would
        # otherwise reach the policy and the handler as `None`, producing an
        # approval card with no arguments and then an AttributeError.
        raise UsageError(f"could not read those arguments ({argv!r}).")
    return parsed


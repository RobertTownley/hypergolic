"""Commands: capability the agent pulls from the filesystem.

A :class:`~hypergolic.harness.primitives.Tool` is declared once and surfaces
three ways: a shim on ``PATH`` at ``/tools/bin/<id>``, a generated
``/tools/<id>/README.md`` that ``--help`` prints, and one line of relevance index
in the system prompt. Invocation travels over a loopback TCP broker
(:mod:`hypergolic.commands.broker`) authorized by a per-session token plus a live
entry in :data:`hypergolic.sandbox.exec_env.EXEC_REGISTRY`.

"""

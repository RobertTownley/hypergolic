"""The route a sandbox shim calls to invoke a command outside its container.

This deliberately punches a hole in the containment boundary, so read the
authorization model before extending it.

What the request may assert, and what it may not:

============  =====================  =========================================
Field         Source                 Trust
============  =====================  =========================================
``command``   the shim's filename    none \u2014 must resolve in the session's set
``argv``      the shell's parsing    none \u2014 validated against ``input_schema``
``cwd``       ``os.getcwd()``        selects among *known* repos only (see the
                                     git tool's ``_host_cwd``); never a raw path
``exec_id``   injected env           not a credential, but must be live and
                                     registered to the same session
``Authorization``  injected env      **yes** \u2014 this alone establishes the session
============  =====================  =========================================

Anything the server can derive is never accepted from the client: not the session
id (the token gives it), not the target container (the exec record gives it), and
not the originating command string (the server issued the exec, so it already
holds it). That last one is a security property, not an ergonomic one \u2014 see
:func:`~hypergolic.commands.broker.approval.originating_command`.

Because the payload is *the parameters of an invocation* rather than a string to
execute, host execution never goes through a shell: a literal ``&&`` inside an
argument is inert data.

Which commands are auto-approved *is* the security boundary. Anything
auto-approved here is reachable by any code executing in the sandbox, including a
compromised dependency the agent just installed. Auto-approve read-only
operations only.
"""

from __future__ import annotations

from hypergolic.commands.broker.invoke import router

__all__ = ["router"]

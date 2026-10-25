class BranchPreservationError(Exception):
    """A running sandbox's branch could not be fetched out to the host.

    Conclude would go on to destroy the gitdir volume — the only copy of the
    branch — so the interactive path blocks on this. It fires only when the
    sandbox is running (a stopped sandbox is never started at conclude and
    preserves nothing); auto-conclude (no agent to bounce to) logs and
    proceeds.
    """

from hypergolic.contrib.workflows import debug_workflow


def test_debug_shape():
    wf = debug_workflow
    assert wf.id == "debug"
    assert wf.name == "Debugging"
    assert [s.id for s in wf.states] == ["investigation", "resolving", "validating"]

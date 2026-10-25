from hypergolic.contrib.workflows import feature_development_workflow


def test_feature_development_shape():
    wf = feature_development_workflow
    assert wf.id == "feature-development"
    assert wf.name == "Product Development"
    assert [s.id for s in wf.states] == [
        "requirements", "planning", "implementation", "review", "summarize",
    ]

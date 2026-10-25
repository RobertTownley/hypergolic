from hypergolic.contrib.workflows import optimize_config_workflow


def test_optimize_config_shape():
    wf = optimize_config_workflow
    assert wf.id == "optimize-config"
    assert wf.name == "Optimize Config"
    assert [s.id for s in wf.states] == [
        "discovery",
        "audit-prompts",
        "audit-tools",
        "audit-skills-roles",
        "audit-workflows",
        "cross-project-review",
        "propose",
        "implement",
        "summarize",
    ]

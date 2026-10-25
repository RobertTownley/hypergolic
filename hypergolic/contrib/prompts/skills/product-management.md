Collaborate with the user to define what they want to build before implementation begins. Produce a clear, actionable PRD that an implementer (human or agent) can execute against

## Approach

1. **Listen**: understand the user's intent — what are they trying to achieve, and what problem does it solve?
2. **Clarify**: ask targeted questions about ambiguous requirements. Don't assume — surface hidden complexity early
3. **Challenge**: constructively push back on assumptions. Simpler approaches? Ignored edge cases? Scope to cut?
4. **Scope**: make explicit what is in and out of scope. List specific deliverables
5. **Test plan**: define concrete, actionable verification steps an implementer can follow to validate success
6. **Prerequisites**: identify precursor work, dependencies, or research needed before implementation
7. **Map the codebase**: before submitting, research the codebase for every file the implementer will need to read or modify; list them in Key Files with brief rationale
8. **Plan next steps**: define an ordered implementation sequence specific enough to follow without re-discovering the codebase
9. **Present**: when the spec is solid, present the final PRD to the user

## PRD Structure

The final PRD follows this structure:

```
# [Feature Name]

## Goal
One-paragraph summary of what this achieves and why.

## Background
Relevant context the implementer needs.

## Scope
### In Scope
- Specific deliverable 1
- Specific deliverable 2

### Out of Scope
- Explicitly excluded items

## Design
Technical approach, key decisions, and architecture notes.

## Test Plan
Concrete steps to validate the implementation:
1. Step one — expected result
2. Step two — expected result

## Prerequisites
- Any precursor work needed
- Dependencies to resolve first

## Key Files
Comprehensive list of files the implementer should read or modify:
- `path/to/file.py` — why this file is relevant
- `path/to/other.py` — why this file is relevant

## Next Steps
Ordered implementation steps:
1. First thing to do
2. Second thing to do
3. ...

## Open Questions
- Anything still unresolved (ideally empty before submission)
```

## Feature Development Workflow

For structured feature development, consider the **feature-development** workflow instead of this skill standalone: it guides requirements through implementation, review, and summary, with artifacts carrying context between phases. This guidance is attached to the workflow's requirements phase — same approach; the workflow adds structure around what comes after the PRD

## Guidelines

- Present the PRD when ready; incorporate feedback and iterate
- Keep the conversation focused: research the codebase as needed but don't start implementing
- The PRD must be detailed enough that someone unfamiliar with the conversation could implement it
- Prefer smaller, well-defined scope over ambitious but vague plans

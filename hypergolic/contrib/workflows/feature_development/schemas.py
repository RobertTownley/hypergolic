"""Output schemas for the feature-development workflow."""
from __future__ import annotations


PRD_SCHEMA = {
    "type": "object",
    "properties": {
        "document": {
            "type": "string",
            "description": "Full PRD in markdown: problem, goals, non-goals, scope, test plan, implementation notes",
        },
        "key_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Files that will need to change or be created",
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Unresolved questions. Should be empty before submitting",
        },
    },
    "required": ["document", "key_files"],
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "document": {
            "type": "string",
            "description": "Ordered, atomic implementation steps in markdown. Each step specifies files, tests, and expected outcome",
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Flagged risks or places the plan may need to change during implementation",
        },
    },
    "required": ["document"],
}

IMPLEMENTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One-paragraph summary of what was built and how it maps to the plan",
        },
        "files_changed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "All files created or modified",
        },
        "test_command": {
            "type": "string",
            "description": "Exact command to run the test suite that covers this change",
        },
        "deviations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Anywhere the implementation differs from the plan and why",
        },
    },
    "required": ["summary", "files_changed", "test_command"],
}

IMPLEMENTATION_BLOCKED_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {
            "type": "string",
            "description": "Why the plan can't be implemented as written — what needs to change in planning",
        },
    },
    "required": ["reason"],
}

REVIEW_PASS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["pass"],
        },
        "notes": {
            "type": "string",
            "description": "Review notes in markdown: what was checked, minor observations, anything worth following up on later",
        },
    },
    "required": ["verdict", "notes"],
}

REVIEW_FAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["fail"],
        },
        "blocking_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific, actionable issues. Each item: file, location, what's wrong, what should change",
        },
    },
    "required": ["verdict", "blocking_issues"],
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "document": {
            "type": "string",
            "description": "Project-record summary: what was built, key design decisions, files changed, test coverage, follow-ups",
        },
    },
    "required": ["document"],
}

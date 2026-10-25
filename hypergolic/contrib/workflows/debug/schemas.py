"""Output schemas for the debug workflow."""
from __future__ import annotations


INVESTIGATION_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {
            "type": "string",
            "description": "Concrete root cause with file path and line reference where applicable. Not a symptom",
        },
        "reproduction": {
            "type": "string",
            "description": "Minimal, exact steps or test command that reliably reproduces the bug",
        },
        "affected_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Files involved in the bug and likely candidates for the fix",
        },
        "evidence": {
            "type": "string",
            "description": "Verbatim error messages, stack traces, or unexpected outputs captured during reproduction",
        },
    },
    "required": ["root_cause", "reproduction", "affected_files"],
}

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One-paragraph description of the fix and why it addresses the root cause",
        },
        "files_changed": {
            "type": "array",
            "items": {"type": "string"},
        },
        "regression_test": {
            "type": "string",
            "description": "Location of the new test that fails without the fix and passes with it",
        },
        "test_command": {
            "type": "string",
            "description": "Exact command to re-run the regression test and related suite",
        },
    },
    "required": ["summary", "files_changed", "regression_test", "test_command"],
}

FIX_BLOCKED_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {
            "type": "string",
            "description": "Why the fix can't proceed as investigated — what needs re-investigation",
        },
    },
    "required": ["reason"],
}

VALIDATION_PASS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass"]},
        "notes": {
            "type": "string",
            "description": "What was re-run, what passed, any follow-ups worth noting",
        },
    },
    "required": ["verdict", "notes"],
}

VALIDATION_FAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["fail"]},
        "failures": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific failures observed: which test, what was expected, what happened",
        },
    },
    "required": ["verdict", "failures"],
}

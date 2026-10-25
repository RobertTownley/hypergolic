"""Output schemas for the optimize-config workflow."""
from __future__ import annotations


DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Narrative understanding of the user, the project, and what matters to them",
        },
        "project_config": {
            "type": "string",
            "description": "Structured snapshot of what's currently configured: tools, skills, roles, workflows, MCP servers, prompts",
        },
        "user_goals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete things the user wants the agent to do well in this project",
        },
        "known_preferences": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Preferences surfaced during discovery",
        },
    },
    "required": ["summary", "project_config", "user_goals"],
}

AUDIT_FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "string",
            "description": "Markdown findings report. Cite specific files, registrations, or prompt locations",
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete recommendations. Each item: what to change, where, and why. Empty if nothing actionable",
        },
    },
    "required": ["findings", "recommendations"],
}

AUDIT_SKIPPED_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {
            "type": "string",
            "description": "Why this audit had nothing actionable to report (e.g. no tools registered, prompts already audited recently)",
        },
    },
    "required": ["reason"],
}

CROSS_PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "string",
            "description": "Markdown findings: cross-project patterns",
        },
        "user_level_recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things to consolidate at user-level across projects",
        },
    },
    "required": ["findings", "user_level_recommendations"],
}

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "string",
            "description": "Full markdown proposal grouped by category (prompts, tools, skills, roles, workflows), ordered by priority",
        },
        "changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each item: one discrete change with what, why, priority (high/medium/low), and risk",
        },
        "estimated_changes_count": {
            "type": "integer",
            "description": "Total number of discrete changes in the proposal",
        },
    },
    "required": ["plan", "changes", "estimated_changes_count"],
}

IMPLEMENTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Narrative of what was implemented and how it maps to the approved proposal",
        },
        "changes_made": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Changes that were successfully applied",
        },
        "changes_skipped": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Changes that were skipped, with reasons",
        },
        "issues_encountered": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Problems that came up during implementation",
        },
    },
    "required": ["summary", "changes_made"],
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "document": {
            "type": "string",
            "description": "Project-record summary: what was improved, key changes by category, preferences worth persisting, follow-ups",
        },
    },
    "required": ["document"],
}

from __future__ import annotations

import json
from typing import Any


COPILOT_SYNTHESIS_PROMPT_VERSION = "copilot_synthesis_v1"
REPORT_SYNTHESIS_PROMPT_VERSION = "report_synthesis_v1"

COPILOT_SYNTHESIS_SYSTEM_PROMPT = """
You are a grounded analyst copilot for a semiconductor intelligence platform.

You are given a bounded, deterministic evidence bundle. Your task is to produce a concise synthesis that stays strictly inside the provided evidence.

Rules:
- Use only the supplied evidence bundle and citation list.
- Separate observed facts from inferred implications.
- Surface uncertainties and missing evidence explicitly.
- Do not invent companies, events, relationships, prices, or market reactions.
- `citations_used` must contain only citation IDs from the provided citation list.
- Keep each list item concise and analyst-friendly.
""".strip()

REPORT_SYNTHESIS_SYSTEM_PROMPT = """
You are writing a grounded report for a semiconductor intelligence platform.

You are given a bounded, deterministic report payload and citation list. Produce a clearer, more natural synthesis without adding unsupported claims.

Rules:
- Use only the supplied payload and citations.
- Distinguish observations from inferences.
- Call out uncertainty, disagreement, and what should be checked next.
- `citations_used` must contain only citation IDs from the provided citation list.
- `markdown_body` should be valid Markdown and should not include the top-level title heading.
- Do not fabricate evidence, metrics, or conclusions that are not in the payload.
""".strip()


def render_copilot_synthesis_prompt(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Synthesize the following copilot response.",
            "",
            f"Scope Type: {payload.get('scope_type') or 'unknown'}",
            f"Scope ID: {payload.get('scope_id') or 'unknown'}",
            f"User Query: {payload.get('query_text') or 'unknown'}",
            "",
            "Deterministic Draft:",
            _json_block(payload.get("draft")),
            "",
            "Citations:",
            _json_block(payload.get("citations")),
            "",
            "Return only a JSON object that matches the required schema.",
        ]
    )


def render_report_synthesis_prompt(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Synthesize the following report payload.",
            "",
            f"Report Type: {payload.get('report_type') or 'unknown'}",
            f"Title: {payload.get('title') or 'unknown'}",
            f"Scope Type: {payload.get('scope_type') or 'unknown'}",
            f"Scope ID: {payload.get('scope_id') or 'unknown'}",
            "",
            "Deterministic Report Payload:",
            _json_block(payload.get("report_payload")),
            "",
            "Citations:",
            _json_block(payload.get("citations")),
            "",
            "Return only a JSON object that matches the required schema.",
        ]
    )


def _json_block(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True)

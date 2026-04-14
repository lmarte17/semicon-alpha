from __future__ import annotations

from typing import Any


EVENT_REVIEW_PROMPT_VERSION = "event_review_v1"

EVENT_REVIEW_SYSTEM_PROMPT = """
You are reviewing a semiconductor news article for a structured event-intelligence pipeline.

Your job is to review the deterministic extraction result and return a grounded, schema-bound assessment.

Rules:
- Stay tightly grounded in the provided article text and deterministic context.
- Do not invent companies, themes, facilities, technologies, or regulators that are not supported by the article.
- When suggesting companies, prefer tracked ticker symbols from the provided tracked-company list.
- When suggesting themes, prefer the provided theme IDs exactly as written.
- If the article is ambiguous, contradictory, commentary-only, or too thin, abstain or mark needs_review instead of forcing certainty.
- Keep summaries short and factual.
- Evidence spans should be short snippets copied from the article context, not long quotations.
""".strip()


def render_event_review_prompt(payload: dict[str, Any]) -> str:
    deterministic = payload.get("deterministic", {})
    article = payload.get("article", {})
    allowed_themes = payload.get("allowed_themes", [])
    tracked_companies = payload.get("tracked_companies", [])
    classification_candidates = payload.get("classification_candidates", [])

    return "\n".join(
        [
            "Review the following article and deterministic event extraction.",
            "",
            f"Headline: {article.get('headline') or 'Unknown'}",
            f"Source: {article.get('source') or 'Unknown'}",
            f"Published At: {article.get('published_at_utc') or 'Unknown'}",
            f"Source URL: {article.get('source_url') or 'Unknown'}",
            "",
            "Article Description:",
            article.get("description") or "None",
            "",
            "Article Excerpt:",
            article.get("excerpt") or "None",
            "",
            "Article Body:",
            article.get("body_text") or "None",
            "",
            "Deterministic Extraction:",
            f"- Event Type: {deterministic.get('event_type') or 'Unknown'}",
            f"- Direction: {deterministic.get('direction') or 'Unknown'}",
            f"- Severity: {deterministic.get('severity') or 'Unknown'}",
            f"- Confidence: {deterministic.get('confidence') or 'Unknown'}",
            f"- Origin Companies: {', '.join(deterministic.get('origin_companies') or []) or 'None'}",
            f"- Mentioned Companies: {', '.join(deterministic.get('mentioned_companies') or []) or 'None'}",
            f"- Primary Segment: {deterministic.get('primary_segment') or 'None'}",
            f"- Secondary Segments: {', '.join(deterministic.get('secondary_segments') or []) or 'None'}",
            f"- Primary Themes: {', '.join(deterministic.get('primary_themes') or []) or 'None'}",
            "",
            "Top Deterministic Classification Candidates:",
            *(
                [
                    f"- {item.get('event_type')}: score={item.get('score')} keywords={', '.join(item.get('matched_keywords') or []) or 'None'}"
                    for item in classification_candidates[:5]
                ]
                or ["- None"]
            ),
            "",
            "Tracked Companies (ticker: name):",
            *([f"- {item}" for item in tracked_companies] or ["- None"]),
            "",
            "Allowed Theme IDs (theme_id: theme_name):",
            *([f"- {item}" for item in allowed_themes] or ["- None"]),
            "",
            "Return only a JSON object that matches the required schema.",
        ]
    )

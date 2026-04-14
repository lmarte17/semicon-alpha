from __future__ import annotations

from typing import Any


ARTICLE_TRIAGE_PROMPT_VERSION = "article_triage_v1"

ARTICLE_TRIAGE_SYSTEM_PROMPT = """
You are reviewing articles for a semiconductor event-intelligence system.

Your task is to decide whether the article is materially relevant to the semiconductor industry and whether it contains an event worth sending into a structured event pipeline.

Be conservative. Prefer abstaining or marking needs_review instead of forcing certainty.

Important rules:
- Focus on semiconductor companies, fabs, tools, materials, packaging, foundry, memory, chip design, regulation, trade policy, export controls, manufacturing capacity, supply-chain constraints, demand signals, and adjacent infrastructure only when they clearly matter to semiconductors.
- Articles about generic consumer tech, broad AI product launches, smartphones, macro markets, or unrelated enterprise software are not event-worthy unless the semiconductor transmission is explicit in the provided text.
- `is_event_worthy` should be true only if the article describes a concrete development rather than general commentary or background context.
- Keep all extracted subject lists short and normalized.
- The reasoning summary must be short and factual.
""".strip()


def render_article_triage_prompt(article: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Review the following article for relevance triage.",
            "",
            f"Headline: {article.get('headline') or 'Unknown'}",
            f"Source: {article.get('source') or 'Unknown'}",
            f"Source URL: {article.get('source_url') or 'Unknown'}",
            f"Canonical URL: {article.get('canonical_url') or 'Unknown'}",
            f"Published At: {article.get('published_at_utc') or 'Unknown'}",
            "",
            "Description:",
            article.get("description") or "None",
            "",
            "Excerpt:",
            article.get("excerpt") or "None",
            "",
            "Discovered Summary Snippet:",
            article.get("discovered_summary_snippet") or "None",
            "",
            "Body Text:",
            article.get("body_text") or "None",
            "",
            "Return only a JSON object that matches the required schema.",
        ]
    )

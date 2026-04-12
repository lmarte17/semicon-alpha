from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from semicon_alpha.models.records import EnrichedArticleRecord
from semicon_alpha.settings import Settings
from semicon_alpha.utils.http import build_http_client
from semicon_alpha.utils.io import (
    normalize_whitespace,
    now_utc,
    sha256_text,
    upsert_parquet,
    write_bytes,
    write_text,
)


LOGGER = logging.getLogger(__name__)


class SourceEnrichmentService:
    def __init__(self, settings: Settings, client=None) -> None:
        self.settings = settings
        self.client = client or build_http_client(settings)
        self.discovered_article_path = settings.processed_dir / "news_articles_discovered.parquet"
        self.enriched_article_path = settings.processed_dir / "news_articles_enriched.parquet"

    def run(self, limit: int = 25, force: bool = False) -> dict[str, int]:
        if not self.discovered_article_path.exists():
            return {"processed_count": 0}
        discovered = pd.read_parquet(self.discovered_article_path)
        if discovered.empty:
            return {"processed_count": 0}
        discovered = discovered.sort_values("last_seen_at_utc", ascending=False)
        existing_success_ids: set[str] = set()
        if self.enriched_article_path.exists():
            existing = pd.read_parquet(self.enriched_article_path)
            if not force:
                success_mask = existing["fetch_status"] == "success"
                existing_success_ids = set(existing.loc[success_mask, "article_id"].tolist())
        if not force and existing_success_ids:
            discovered = discovered[~discovered["article_id"].isin(existing_success_ids)]
        candidates = discovered.head(limit)
        records = [
            self.enrich_article(row["article_id"], row["source_url"])
            for _, row in candidates.iterrows()
        ]
        upsert_parquet(
            self.enriched_article_path,
            records,
            unique_keys=["article_id"],
            sort_by=["fetched_at_utc"],
        )
        return {"processed_count": len(records)}

    def enrich_article(self, article_id: str, source_url: str) -> EnrichedArticleRecord:
        fetched_at = now_utc()
        try:
            response = self.client.get(source_url)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - exercised in integration use
            return EnrichedArticleRecord(
                article_id=article_id,
                source_url=source_url,
                fetch_status="error",
                fetched_at_utc=fetched_at,
                error_message=str(exc),
            )

        content_type = response.headers.get("content-type")
        if content_type and "html" not in content_type and "xml" not in content_type and "text/" not in content_type:
            raw_path = self._raw_source_path(fetched_at, article_id, content_type)
            write_bytes(raw_path, response.content)
            return EnrichedArticleRecord(
                article_id=article_id,
                source_url=source_url,
                fetch_status="unsupported_mime",
                http_status=response.status_code,
                content_type=content_type,
                fetched_at_utc=fetched_at,
                raw_html_path=str(raw_path),
                error_message=f"Unsupported content type: {content_type}",
            )

        html = response.text
        raw_path = self._raw_source_path(fetched_at, article_id, content_type or "text/html")
        write_text(raw_path, html)
        metadata = extract_article_metadata(html=html, source_url=source_url)
        return EnrichedArticleRecord(
            article_id=article_id,
            source_url=source_url,
            canonical_url=metadata["canonical_url"],
            fetch_status="success",
            http_status=response.status_code,
            content_type=content_type,
            fetched_at_utc=fetched_at,
            published_at_utc=metadata["published_at_utc"],
            title=metadata["title"],
            site_name=metadata["site_name"],
            author=metadata["author"],
            excerpt=metadata["excerpt"],
            description=metadata["description"],
            body_text=metadata["body_text"],
            raw_html_path=str(raw_path),
            content_sha256=sha256_text(metadata["body_text"] or html),
        )

    def _raw_source_path(self, fetched_at: datetime, article_id: str, content_type: str) -> Path:
        extension = ".html"
        if "pdf" in content_type:
            extension = ".pdf"
        elif "json" in content_type:
            extension = ".json"
        elif "xml" in content_type:
            extension = ".xml"
        elif "text/plain" in content_type:
            extension = ".txt"
        return (
            self.settings.raw_dir
            / "source_articles"
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / f"{article_id}{extension}"
        )


def extract_article_metadata(html: str, source_url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    jsonld_objects = _extract_jsonld_objects(soup)
    canonical_url = (
        _link_href(soup, "canonical")
        or _meta_content(soup, property_name="og:url")
        or source_url
    )
    published_at = _extract_published_at(soup, jsonld_objects)
    title = (
        _meta_content(soup, property_name="og:title")
        or _meta_content(soup, name="twitter:title")
        or _jsonld_value(jsonld_objects, "headline")
        or normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else None)
        or normalize_whitespace(_first_text(soup.select_one("h1")))
    )
    author = (
        _meta_content(soup, name="author")
        or _meta_content(soup, property_name="article:author")
        or _jsonld_author(jsonld_objects)
    )
    description = (
        _meta_content(soup, name="description")
        or _meta_content(soup, property_name="og:description")
        or _jsonld_value(jsonld_objects, "description")
    )
    site_name = (
        _meta_content(soup, property_name="og:site_name")
        or _jsonld_value(jsonld_objects, "publisher.name")
        or urlparse(source_url).netloc.lower().removeprefix("www.")
    )
    body_text = extract_body_text(soup)
    excerpt = normalize_whitespace(body_text[:400] if body_text else description)
    return {
        "canonical_url": canonical_url,
        "published_at_utc": published_at,
        "title": title,
        "site_name": site_name,
        "author": author,
        "description": description,
        "body_text": body_text,
        "excerpt": excerpt,
    }


def extract_body_text(soup: BeautifulSoup) -> str | None:
    working = BeautifulSoup(str(soup), "lxml")
    for tag_name in ("script", "style", "noscript", "header", "footer", "nav", "aside", "form"):
        for node in working.find_all(tag_name):
            node.decompose()

    candidates: list[tuple[int, Tag]] = []
    selectors = [
        "article",
        "main",
        "[role='main']",
        "div[class*='article']",
        "div[class*='content']",
        "div[class*='post']",
        "div[class*='entry']",
        "section[class*='article']",
    ]
    for selector in selectors:
        for node in working.select(selector):
            score = _node_text_score(node)
            if score > 0:
                candidates.append((score, node))

    body = working.body or working
    body_score = _node_text_score(body)
    if body_score > 0:
        candidates.append((body_score, body))
    if not candidates:
        return None
    best_node = max(candidates, key=lambda item: item[0])[1]
    paragraphs = []
    for paragraph in best_node.find_all("p"):
        text = normalize_whitespace(paragraph.get_text(" ", strip=True))
        if text and len(text) >= 40:
            paragraphs.append(text)
    if not paragraphs:
        text = normalize_whitespace(best_node.get_text("\n", strip=True))
        return text if text and len(text) >= 80 else None
    return "\n\n".join(paragraphs)


def _extract_published_at(
    soup: BeautifulSoup, jsonld_objects: list[dict]
) -> datetime | None:
    candidates = [
        _meta_content(soup, property_name="article:published_time"),
        _meta_content(soup, property_name="og:published_time"),
        _meta_content(soup, name="pubdate"),
        _meta_content(soup, name="publish-date"),
        _meta_content(soup, name="date"),
        _meta_content(soup, name="dc.date"),
        _time_datetime(soup),
        _jsonld_value(jsonld_objects, "datePublished"),
        _jsonld_value(jsonld_objects, "dateCreated"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = date_parser.parse(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue
    return None


def _time_datetime(soup: BeautifulSoup) -> str | None:
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        return time_tag["datetime"]
    return None


def _link_href(soup: BeautifulSoup, rel_name: str) -> str | None:
    tag = soup.find("link", rel=lambda values: values and rel_name in values)
    if tag and tag.get("href"):
        return tag["href"]
    return None


def _meta_content(
    soup: BeautifulSoup,
    *,
    name: str | None = None,
    property_name: str | None = None,
) -> str | None:
    attrs = {}
    if name:
        attrs["name"] = name
    if property_name:
        attrs["property"] = property_name
    tag = soup.find("meta", attrs=attrs)
    if tag and tag.get("content"):
        return normalize_whitespace(tag["content"])
    return None


def _extract_jsonld_objects(soup: BeautifulSoup) -> list[dict]:
    objects: list[dict] = []
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        objects.extend(_flatten_jsonld(parsed))
    return objects


def _flatten_jsonld(payload: object) -> list[dict]:
    if isinstance(payload, list):
        flattened: list[dict] = []
        for item in payload:
            flattened.extend(_flatten_jsonld(item))
        return flattened
    if isinstance(payload, dict):
        flattened = [payload]
        if "@graph" in payload:
            flattened.extend(_flatten_jsonld(payload["@graph"]))
        return flattened
    return []


def _jsonld_value(objects: list[dict], dotted_key: str) -> str | None:
    key_parts = dotted_key.split(".")
    for obj in objects:
        candidate: object = obj
        for part in key_parts:
            if not isinstance(candidate, dict) or part not in candidate:
                candidate = None
                break
            candidate = candidate[part]
        if isinstance(candidate, str):
            return normalize_whitespace(candidate)
    return None


def _jsonld_author(objects: list[dict]) -> str | None:
    for obj in objects:
        author = obj.get("author")
        if isinstance(author, str):
            return normalize_whitespace(author)
        if isinstance(author, dict):
            return normalize_whitespace(author.get("name"))
        if isinstance(author, list):
            names = []
            for item in author:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict) and item.get("name"):
                    names.append(item["name"])
            if names:
                return normalize_whitespace(", ".join(names))
    return None


def _node_text_score(node: Tag) -> int:
    total = 0
    for paragraph in node.find_all("p"):
        text = normalize_whitespace(paragraph.get_text(" ", strip=True))
        if text and len(text) >= 40:
            total += len(text)
    return total


def _first_text(node: Tag | None) -> str | None:
    if node is None:
        return None
    return normalize_whitespace(node.get_text(" ", strip=True))

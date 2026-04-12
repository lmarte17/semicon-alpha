from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from semicon_alpha.models.records import (
    ArticleObservationRecord,
    DiscoveredArticleRecord,
    SnapshotMetadata,
    SourceRegistryRecord,
)
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.http import build_http_client
from semicon_alpha.utils.io import (
    normalize_whitespace,
    now_utc,
    sha256_text,
    stable_id,
    upsert_parquet,
    write_text,
)


LOGGER = logging.getLogger(__name__)

WRITTEN_AT_PATTERN = re.compile(
    r"written = new Date\(Date\.UTC\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+),\d+\)\);"
)
AGE_CLASS_PATTERN = re.compile(r"^h(\d+)$")
ICON_ID_PATTERN = re.compile(r"dom\.(\d+)\.ico")


class LithosIngestionService:
    def __init__(self, settings: Settings, client=None) -> None:
        self.settings = settings
        self.client = client or build_http_client(settings)
        self.catalog = DuckDBCatalog(settings)
        self.snapshot_table_path = settings.processed_dir / "lithos_snapshots.parquet"
        self.source_registry_path = settings.processed_dir / "news_source_registry.parquet"
        self.article_observation_path = settings.processed_dir / "news_article_observations.parquet"
        self.discovered_article_path = settings.processed_dir / "news_articles_discovered.parquet"

    def run(self) -> dict[str, object]:
        fetched_at = now_utc()
        response = self.client.get(self.settings.lithos_url)
        response.raise_for_status()
        html = response.text
        content_sha = sha256_text(html)
        snapshot_id = stable_id(
            "lithos_snapshot",
            self.settings.lithos_url,
            fetched_at.isoformat(),
            content_sha,
        )
        raw_path = self._snapshot_raw_path(fetched_at, snapshot_id)
        write_text(raw_path, html)
        site_written_at = parse_lithos_written_at(html)
        snapshot_record = SnapshotMetadata(
            snapshot_id=snapshot_id,
            topic="semicon",
            source_url=self.settings.lithos_url,
            fetched_at_utc=fetched_at,
            site_written_at_utc=site_written_at,
            http_status=response.status_code,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            raw_path=str(raw_path),
            content_sha256=content_sha,
        )
        upsert_parquet(self.snapshot_table_path, [snapshot_record], unique_keys=["snapshot_id"])

        source_records = parse_source_registry(html, fetched_at, snapshot_id)
        source_lookup = {record.icon_id: record.source_slug for record in source_records if record.icon_id}
        observation_records = parse_article_observations(
            html=html,
            snapshot_id=snapshot_id,
            discovered_at=fetched_at,
            source_lookup=source_lookup,
            lithos_base_url=self.settings.lithos_url,
        )

        upsert_parquet(
            self.source_registry_path,
            source_records,
            unique_keys=["source_id"],
            sort_by=["scraped_at_utc"],
        )
        upsert_parquet(
            self.article_observation_path,
            observation_records,
            unique_keys=["observation_id"],
            sort_by=["discovered_at_utc"],
        )
        master_records = self._merge_discovered_articles(observation_records)
        upsert_parquet(
            self.discovered_article_path,
            master_records,
            unique_keys=["article_id"],
            sort_by=["last_seen_at_utc"],
        )
        self.catalog.refresh_processed_views()

        return {"snapshot_id": snapshot_id, "article_count": len(observation_records)}

    def _merge_discovered_articles(
        self, observation_records: list[ArticleObservationRecord]
    ) -> list[DiscoveredArticleRecord]:
        existing_map: dict[str, dict] = {}
        if self.discovered_article_path.exists():
            existing_frame = pd.read_parquet(self.discovered_article_path)
            existing_map = {
                row["article_id"]: row for row in existing_frame.to_dict(orient="records")
            }

        merged: dict[str, DiscoveredArticleRecord] = {}
        for observation in observation_records:
            previous = existing_map.get(observation.article_id)
            first_seen = observation.discovered_at_utc
            observation_count = 1
            if previous:
                first_seen = _coerce_datetime(previous["first_discovered_at_utc"])
                observation_count = int(previous["observation_count"]) + 1
            merged[observation.article_id] = DiscoveredArticleRecord(
                article_id=observation.article_id,
                source_url=observation.source_url,
                title=observation.title,
                summary_snippet=observation.summary_snippet,
                source_domain=observation.source_domain,
                source_slug=observation.source_slug,
                icon_id=observation.icon_id,
                first_discovered_at_utc=first_seen,
                last_seen_at_utc=observation.discovered_at_utc,
                latest_snapshot_id=observation.snapshot_id,
                latest_lithos_age_bucket_label=observation.lithos_age_bucket_label,
                latest_lithos_age_bucket_hours=observation.lithos_age_bucket_hours,
                latest_is_urgent=observation.is_urgent,
                latest_image_url=observation.image_url,
                latest_position_index=observation.position_index,
                observation_count=observation_count,
            )
        return list(merged.values())

    def _snapshot_raw_path(self, fetched_at: datetime, snapshot_id: str) -> Path:
        return (
            self.settings.raw_dir
            / "lithos_snapshots"
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / f"{fetched_at.strftime('%H%M%S')}_{snapshot_id}.html"
        )


def parse_lithos_written_at(html: str) -> datetime | None:
    match = WRITTEN_AT_PATTERN.search(html)
    if not match:
        return None
    year, month_zero, day, hour, minute, second = [int(value) for value in match.groups()]
    return datetime(
        year,
        month_zero + 1,
        day,
        hour,
        minute,
        second,
        tzinfo=timezone.utc,
    )


def parse_source_registry(
    html: str, fetched_at: datetime, snapshot_id: str
) -> list[SourceRegistryRecord]:
    soup = BeautifulSoup(html, "lxml")
    registry_table = soup.find("table", class_="domlist")
    if registry_table is None:
        return []
    records: list[SourceRegistryRecord] = []
    for cell in registry_table.select("td.domlist"):
        link = cell.find("a", href=True)
        if link is None:
            continue
        source_url = link["href"]
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower().removeprefix("www.")
        source_slug = normalize_whitespace(link.get_text(" ", strip=True)) or domain
        icon_id = _extract_icon_id(cell)
        data_cells = cell.select("td.dlnest_data")
        freshness_text = None
        status_flag = None
        if data_cells:
            freshness_text = normalize_whitespace(data_cells[0].get_text(" ", strip=True))
            if len(data_cells) > 1:
                status_flag = _extract_status_flag(data_cells[1])
        records.append(
            SourceRegistryRecord(
                source_id=stable_id("source", domain, source_slug),
                source_slug=source_slug,
                source_domain=domain,
                lithos_source_url=source_url,
                freshness_text=freshness_text,
                status_flag=status_flag,
                icon_id=icon_id,
                source_topic="semicon",
                scraped_at_utc=fetched_at,
                snapshot_id=snapshot_id,
            )
        )
    return records


def parse_article_observations(
    html: str,
    snapshot_id: str,
    discovered_at: datetime,
    source_lookup: dict[str, str],
    lithos_base_url: str,
) -> list[ArticleObservationRecord]:
    soup = BeautifulSoup(html, "lxml")
    news_table = soup.find("table", class_="news")
    if news_table is None:
        return []
    records: list[ArticleObservationRecord] = []
    position = 0
    for paragraph in news_table.find_all("p"):
        link = paragraph.find("a", href=True)
        title_node = paragraph.find("b")
        if link is None or title_node is None:
            continue
        href = link["href"]
        if not href.startswith("http"):
            continue
        title = _clean_title(title_node.get_text(" ", strip=True))
        if not title:
            continue
        position += 1
        source_domain = urlparse(href).netloc.lower().removeprefix("www.")
        icon_id = _extract_icon_id(paragraph)
        source_slug = source_lookup.get(icon_id or "", source_domain)
        age_label, age_hours = _find_age_bucket(paragraph)
        snippet = _extract_snippet(paragraph, title)
        wrapper = _find_content_wrapper(paragraph, news_table)
        image_tag = wrapper.find("img", class_="news") if wrapper else None
        image_url = None
        if image_tag and image_tag.get("src"):
            image_url = urljoin(lithos_base_url, image_tag["src"])
        is_urgent = bool(paragraph.find("img", src=re.compile(r"siren\.gif")))
        article_id = stable_id("article", href)
        records.append(
            ArticleObservationRecord(
                observation_id=stable_id("article_obs", snapshot_id, article_id, position),
                article_id=article_id,
                snapshot_id=snapshot_id,
                discovered_at_utc=discovered_at,
                source_url=href,
                title=title,
                summary_snippet=snippet,
                source_domain=source_domain,
                source_slug=source_slug,
                icon_id=icon_id,
                lithos_age_bucket_label=age_label,
                lithos_age_bucket_hours=age_hours,
                is_urgent=is_urgent,
                image_url=image_url,
                position_index=position,
            )
        )
    return records


def _find_content_wrapper(node: Tag, boundary: Tag) -> Tag | None:
    current = node
    while current and current is not boundary:
        if current.name == "div":
            classes = current.get("class", [])
            if any(class_name == "content" or AGE_CLASS_PATTERN.match(class_name) or class_name == "hexpired" for class_name in classes):
                return current
        current = current.parent if isinstance(current.parent, Tag) else None
    return None


def _find_age_bucket(node: Tag) -> tuple[str | None, int | None]:
    current: Tag | None = node
    while current:
        classes = current.get("class", [])
        for class_name in classes:
            if class_name == "hexpired":
                return "expired", None
            match = AGE_CLASS_PATTERN.match(class_name)
            if match:
                return class_name, int(match.group(1))
        current = current.parent if isinstance(current.parent, Tag) else None
    return None, None


def _extract_snippet(paragraph: Tag, title: str) -> str | None:
    raw_text = normalize_whitespace(paragraph.get_text(" ", strip=True))
    if not raw_text:
        return None
    text_without_title = raw_text.replace(title, "", 1).strip()
    snippet = text_without_title.lstrip("-\u2013\u2014 ")
    return normalize_whitespace(snippet)


def _extract_icon_id(node: Tag) -> str | None:
    icon = node.find("img", src=ICON_ID_PATTERN)
    if icon is None:
        return None
    match = ICON_ID_PATTERN.search(icon["src"])
    return match.group(1) if match else None


def _extract_status_flag(node: Tag) -> str | None:
    icon = node.find("img", src=True)
    if icon is None:
        return None
    source = icon["src"]
    if source.endswith("warn.ico"):
        return "warn"
    if source.endswith("error.ico"):
        return "error"
    return normalize_whitespace(Path(source).stem)


def _clean_title(value: str) -> str:
    cleaned = normalize_whitespace(value) or ""
    return cleaned.lstrip("\u2009\u200a\u2008\u2022\u00b7- ")


def _coerce_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return date_parser.isoparse(value)

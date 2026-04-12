from pathlib import Path

from semicon_alpha.ingestion.lithos import (
    parse_article_observations,
    parse_lithos_written_at,
    parse_source_registry,
)


def test_parse_lithos_written_at():
    fixture = Path("tests/fixtures/lithos_sample.html").read_text(encoding="utf-8")
    written_at = parse_lithos_written_at(fixture)
    assert written_at is not None
    assert written_at.isoformat() == "2026-04-02T19:55:21+00:00"


def test_parse_source_registry():
    fixture = Path("tests/fixtures/lithos_sample.html").read_text(encoding="utf-8")
    records = parse_source_registry(
        fixture,
        fetched_at=parse_lithos_written_at(fixture),
        snapshot_id="snapshot_1",
    )
    assert len(records) == 2
    assert records[0].source_slug == "amd"
    assert records[1].status_flag == "warn"


def test_parse_article_observations():
    fixture = Path("tests/fixtures/lithos_sample.html").read_text(encoding="utf-8")
    observations = parse_article_observations(
        html=fixture,
        snapshot_id="snapshot_1",
        discovered_at=parse_lithos_written_at(fixture),
        source_lookup={"10": "amd", "20": "eetimes", "154": "electronicsweekly"},
        lithos_base_url="https://lithosgraphein.com/",
    )
    assert len(observations) == 3
    assert observations[0].title == "NVIDIA invests in packaging capacity"
    assert observations[0].lithos_age_bucket_hours == 5
    assert observations[0].image_url == "https://lithosgraphein.com/images/news.1.jpg"
    assert observations[1].is_urgent is True
    assert observations[1].lithos_age_bucket_hours == 34
    assert observations[2].source_slug == "electronicsweekly"

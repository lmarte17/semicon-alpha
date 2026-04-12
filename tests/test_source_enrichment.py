from pathlib import Path

from semicon_alpha.ingestion.source_enrichment import extract_article_metadata


def test_extract_article_metadata():
    fixture = Path("tests/fixtures/article_sample.html").read_text(encoding="utf-8")
    metadata = extract_article_metadata(
        html=fixture,
        source_url="https://publisher.example.com/sample-article?foo=bar",
    )
    assert metadata["canonical_url"] == "https://publisher.example.com/sample-article"
    assert metadata["title"] == "AI supply chain bottleneck widens"
    assert metadata["site_name"] == "Publisher Example"
    assert metadata["author"] == "Jane Analyst"
    assert metadata["published_at_utc"].isoformat() == "2026-04-02T12:30:00+00:00"
    assert "Advanced packaging constraints" in metadata["body_text"]

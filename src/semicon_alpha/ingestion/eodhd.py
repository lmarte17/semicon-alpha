from __future__ import annotations

"""Compatibility aliases for the former EODHD market ingestion module."""

from semicon_alpha.ingestion.fmp import (
    FMPClient as EODHDClient,
    FMPIngestionService as EODHDIngestionService,
    FMPRequestError as EODHDRequestError,
)

__all__ = ["EODHDClient", "EODHDIngestionService", "EODHDRequestError"]

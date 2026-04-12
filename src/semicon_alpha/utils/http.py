from __future__ import annotations

import httpx

from semicon_alpha.settings import Settings


def build_http_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=settings.request_timeout_seconds,
        headers={"User-Agent": settings.user_agent},
    )

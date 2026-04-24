from __future__ import annotations

import logging
from datetime import datetime

import httpx

from .analyze import Analysis
from .models import Post

log = logging.getLogger(__name__)

SLACK_MAX_CHARS = 2900


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _top_line(idx: int, post: Post) -> str:
    return (
        f"{idx}. *<{post.url}|{post.author_name}>* · {post.platform.upper()} "
        f"· ❤️ {post.likes:,} 💬 {post.comments:,} 🔁 {post.reposts:,}\n"
        f"    _{_truncate(post.text, 120)}_"
    )


def _top_section(posts: list[Post]) -> str:
    if not posts:
        return "*🔥 Top posts (24h)*\n_No posts in the last 24h._"
    lines = ["*🔥 Top posts (24h)*"]
    for idx, post in enumerate(posts[:5], start=1):
        lines.append(_top_line(idx, post))
    return "\n".join(lines)


def _chunk(text: str, limit: int = SLACK_MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at <= 0:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def build_payloads(
    *,
    date: datetime,
    top_posts: list[Post],
    all_posts: list[Post],
    analysis: Analysis,
    errors: list[str],
) -> list[dict]:
    header = f"*🚀 Founder Intel — {date.strftime('%a %b %d')}*"
    counts = f"_{len(all_posts)} posts · {len(top_posts)} ranked_"
    if errors:
        counts += "\n" + "\n".join(f":warning: {e[:120]}" for e in errors[:2])

    sections = [
        f"{header}\n{counts}",
        _top_section(top_posts),
        analysis.patterns_markdown.strip(),
        analysis.drafts_markdown.strip(),
    ]
    body = "\n\n".join(s for s in sections if s)

    return [
        {"text": chunk, "unfurl_links": False, "unfurl_media": False}
        for chunk in _chunk(body)
    ]


def post_to_slack(webhook_url: str, payloads: list[dict]) -> None:
    with httpx.Client(timeout=30) as client:
        for idx, payload in enumerate(payloads, start=1):
            response = client.post(webhook_url, json=payload)
            if response.status_code >= 300:
                log.error(
                    "Slack POST %s/%s failed: %s %s",
                    idx,
                    len(payloads),
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()
            log.info("Slack POST %s/%s ok", idx, len(payloads))

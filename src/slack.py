from __future__ import annotations

import logging
from datetime import datetime

import httpx

from .analyze import Analysis
from .models import Post
from .rank import group_by_author

log = logging.getLogger(__name__)

SLACK_MAX_CHARS_PER_SECTION = 2800


def _truncate(text: str, limit: int = 240) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _format_engagement(post: Post) -> str:
    return (
        f"❤️ {post.likes:,} · 💬 {post.comments:,} · 🔁 {post.reposts:,}  "
        f"(score {post.engagement:,})"
    )


def _top_posts_section(posts: list[Post]) -> str:
    if not posts:
        return "_No posts broke through in the last 24h._"
    lines: list[str] = ["*🔥 Top viral posts (last 24h)*"]
    for idx, post in enumerate(posts, start=1):
        lines.append(
            f"{idx}. *<{post.url}|{post.author_name}>* · "
            f"{post.platform.upper()} · {_format_engagement(post)}\n"
            f"    {_truncate(post.text)}"
        )
    return "\n".join(lines)


def _per_author_section(posts: list[Post]) -> str:
    grouped = group_by_author(posts)
    if not grouped:
        return "_No per-author activity._"
    lines: list[str] = ["*📥 Per-influencer feed*"]
    for author, author_posts in grouped.items():
        lines.append(f"\n*{author}* ({len(author_posts)})")
        for post in author_posts[:5]:
            lines.append(
                f"• [{post.platform.upper()}] "
                f"<{post.url}|{_truncate(post.text, 140)}> — "
                f"{_format_engagement(post)}"
            )
    joined = "\n".join(lines)
    if len(joined) > SLACK_MAX_CHARS_PER_SECTION * 2:
        joined = joined[: SLACK_MAX_CHARS_PER_SECTION * 2] + "\n…(truncated)"
    return joined


def _chunk(text: str, limit: int = SLACK_MAX_CHARS_PER_SECTION) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
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
    header = f"🚀 *Founder Intel — {date.strftime('%A, %B %d %Y')}*"
    if errors:
        header += "\n" + "\n".join(f":warning: {e}" for e in errors)

    sections = [
        header,
        _top_posts_section(top_posts),
        f"*📊 Patterns this week*\n{analysis.patterns_markdown}",
        f"*✍️ Your drafts (Emir-style)*\n{analysis.drafts_markdown}",
    ]
    main_text = "\n\n────────────────\n\n".join(sections)

    payloads: list[dict] = []
    for chunk in _chunk(main_text):
        payloads.append({"text": chunk, "unfurl_links": False, "unfurl_media": False})

    for chunk in _chunk(_per_author_section(all_posts)):
        payloads.append({"text": chunk, "unfurl_links": False, "unfurl_media": False})

    return payloads


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

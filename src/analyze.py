from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import anthropic

from .config import Settings
from .models import Post

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MODEL = "claude-sonnet-4-6"


@dataclass
class Analysis:
    patterns_markdown: str
    drafts_markdown: str


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_posts_for_prompt(posts: list[Post]) -> str:
    lines: list[str] = []
    for idx, post in enumerate(posts, start=1):
        text = post.text.replace("\n", " ").strip()
        if len(text) > 600:
            text = text[:600].rstrip() + "…"
        lines.append(
            f"[{idx}] {post.author_name} · {post.platform.upper()} · "
            f"likes={post.likes} comments={post.comments} reposts={post.reposts} "
            f"engagement={post.engagement}\n"
            f"    URL: {post.url}\n"
            f"    {text}"
        )
    return "\n\n".join(lines) if lines else "(no posts in window)"


def _extract_text(message: anthropic.types.Message) -> str:
    return "".join(block.text for block in message.content if block.type == "text").strip()


def generate(settings: Settings, top_posts: list[Post]) -> Analysis:
    if not top_posts:
        empty = "_No posts fetched in the last 24h window._"
        return Analysis(patterns_markdown=empty, drafts_markdown=empty)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    analysis_system = _load_prompt("analysis.md")
    draft_system = _load_prompt("draft.md")
    posts_block = _format_posts_for_prompt(top_posts)

    log.info("calling Claude for pattern analysis on %d posts", len(top_posts))
    patterns_msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[
            {
                "type": "text",
                "text": analysis_system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Top posts from the last 24 hours:\n\n{posts_block}",
            }
        ],
    )
    patterns_markdown = _extract_text(patterns_msg)

    log.info("calling Claude for draft generation")
    drafts_msg = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[
            {
                "type": "text",
                "text": draft_system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    "## Today's pattern analysis\n\n"
                    f"{patterns_markdown}\n\n"
                    "## Top 5 posts to ride\n\n"
                    f"{_format_posts_for_prompt(top_posts[:5])}"
                ),
            }
        ],
    )
    drafts_markdown = _extract_text(drafts_msg)

    return Analysis(
        patterns_markdown=patterns_markdown,
        drafts_markdown=drafts_markdown,
    )

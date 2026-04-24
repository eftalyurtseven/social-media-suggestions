from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from dateutil import parser as dateparser

Platform = Literal["linkedin", "x"]


@dataclass
class Influencer:
    name: str
    role: str
    company: str
    linkedin_url: str | None
    x_url: str | None
    why_relevant: str


@dataclass
class Post:
    author_name: str
    author_company: str
    platform: Platform
    url: str
    text: str
    posted_at: datetime
    likes: int
    comments: int
    reposts: int

    @property
    def engagement(self) -> int:
        return self.likes + self.comments * 3 + self.reposts * 2


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return 0
        try:
            return int(float(cleaned))
        except ValueError:
            return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    try:
        dt = dateparser.parse(str(value))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _first(record: dict, *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def linkedin_post_from_record(record: dict, influencer: Influencer) -> Post | None:
    posted_at = _to_datetime(_first(record, "date_posted", "posted_at", "postedAt", "date"))
    url = _first(record, "url", "post_url", "link")
    text = _first(record, "post_text", "description", "text", "content") or ""
    if posted_at is None or not url:
        return None
    return Post(
        author_name=influencer.name,
        author_company=influencer.company,
        platform="linkedin",
        url=str(url),
        text=str(text),
        posted_at=posted_at,
        likes=_to_int(_first(record, "num_likes", "likes", "reactions", "num_reactions")),
        comments=_to_int(_first(record, "num_comments", "comments")),
        reposts=_to_int(_first(record, "num_shares", "shares", "reposts", "num_reposts")),
    )


def x_post_from_entry(entry: dict, influencer: Influencer) -> Post | None:
    """Normalize a single tweet entry from inside a profile record's ``posts`` array."""
    posted_at = _to_datetime(_first(entry, "date_posted", "created_at", "posted_at"))
    url = _first(entry, "post_url", "url", "tweet_url")
    text = _first(entry, "description", "text", "tweet_text", "content") or ""
    if posted_at is None or not url:
        return None
    return Post(
        author_name=influencer.name,
        author_company=influencer.company,
        platform="x",
        url=str(url),
        text=str(text),
        posted_at=posted_at,
        likes=_to_int(_first(entry, "likes", "favorite_count", "num_likes")),
        comments=_to_int(_first(entry, "replies", "reply_count", "num_replies", "comments")),
        reposts=_to_int(_first(entry, "reposts", "retweets", "retweet_count", "num_reposts")),
    )

from __future__ import annotations

from collections import defaultdict

from .models import Post


def top_n(posts: list[Post], n: int = 10) -> list[Post]:
    return sorted(posts, key=lambda p: p.engagement, reverse=True)[:n]


def group_by_author(posts: list[Post]) -> dict[str, list[Post]]:
    grouped: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        grouped[post.author_name].append(post)
    for name in grouped:
        grouped[name].sort(key=lambda p: p.engagement, reverse=True)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))

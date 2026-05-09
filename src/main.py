from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from .analyze import generate as generate_analysis
from .brightdata import fetch_recent_posts
from .config import Settings, load_influencers
from .rank import top_n
from .slack import build_payloads, post_to_slack

log = logging.getLogger("founder_intel")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def _run(args: argparse.Namespace) -> int:
    settings = Settings.from_env(require_slack=not args.dry_run)
    influencers = load_influencers()

    if args.only:
        name_lc = args.only.lower()
        influencers = [inf for inf in influencers if inf.name.lower() == name_lc]
        if not influencers:
            log.error("no influencer matched --only=%s", args.only)
            return 2

    log.info("loaded %d influencers", len(influencers))

    window_hours = max(1, args.days) * 24
    posts, errors = await fetch_recent_posts(settings, influencers, window_hours=window_hours)
    log.info("fetched %d posts within %dd window; errors=%d", len(posts), args.days, len(errors))

    if args.dump_posts:
        sorted_posts = sorted(posts, key=lambda p: p.engagement, reverse=True)
        dump = [
            {
                "author": p.author_name,
                "company": p.author_company,
                "platform": p.platform,
                "url": p.url,
                "posted_at": p.posted_at.isoformat(),
                "likes": p.likes,
                "comments": p.comments,
                "reposts": p.reposts,
                "engagement": p.engagement,
                "text": p.text,
            }
            for p in sorted_posts
        ]
        print(json.dumps({"count": len(dump), "errors": errors, "posts": dump}, ensure_ascii=False, indent=2))
        return 0

    top = top_n(posts, n=10)
    analysis = generate_analysis(settings, top)

    payloads = build_payloads(
        date=datetime.now(timezone.utc),
        top_posts=top,
        all_posts=posts,
        analysis=analysis,
        errors=errors,
        window_days=args.days,
    )

    if args.dry_run:
        for idx, payload in enumerate(payloads, start=1):
            print(f"\n===== Slack message {idx}/{len(payloads)} =====")
            print(payload["text"])
        print(f"\n[dry-run] would send {len(payloads)} Slack messages")
        return 0

    post_to_slack(settings.slack_webhook_url, payloads)
    log.info("digest delivered (%d messages)", len(payloads))
    return 0


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(description="Founder Intel daily digest")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Slack payloads instead of POSTing",
    )
    parser.add_argument(
        "--only",
        help="Fetch only the named influencer (for smoke tests)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Look-back window in days (default 1)",
    )
    parser.add_argument(
        "--dump-posts",
        action="store_true",
        help="Print all fetched posts as JSON and exit (no Claude, no Slack)",
    )
    args = parser.parse_args()
    try:
        exit_code = asyncio.run(_run(args))
    except Exception:
        log.exception("fatal error")
        sys.exit(1)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

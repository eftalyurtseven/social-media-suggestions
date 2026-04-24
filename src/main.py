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

    posts, errors = await fetch_recent_posts(settings, influencers)
    log.info("fetched %d posts within 24h window; errors=%d", len(posts), len(errors))

    top = top_n(posts, n=10)
    analysis = generate_analysis(settings, top)

    payloads = build_payloads(
        date=datetime.now(timezone.utc),
        top_posts=top,
        all_posts=posts,
        analysis=analysis,
        errors=errors,
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
    args = parser.parse_args()
    try:
        exit_code = asyncio.run(_run(args))
    except Exception:
        log.exception("fatal error")
        sys.exit(1)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

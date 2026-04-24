from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

from .models import Influencer

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "founder_influencers.csv"


@dataclass
class Settings:
    brightdata_api_key: str
    brightdata_linkedin_dataset_id: str
    brightdata_x_dataset_id: str
    anthropic_api_key: str
    slack_webhook_url: str

    @classmethod
    def from_env(cls, *, require_slack: bool = True) -> "Settings":
        def need(key: str, *, required: bool = True) -> str:
            value = os.environ.get(key, "").strip()
            if required and not value:
                raise RuntimeError(f"Missing required env var: {key}")
            return value

        return cls(
            brightdata_api_key=need("BRIGHTDATA_API_KEY"),
            brightdata_linkedin_dataset_id=need("BRIGHTDATA_LINKEDIN_DATASET_ID"),
            brightdata_x_dataset_id=need("BRIGHTDATA_X_DATASET_ID"),
            anthropic_api_key=need("ANTHROPIC_API_KEY"),
            slack_webhook_url=need("SLACK_WEBHOOK_URL", required=require_slack),
        )


def _canonicalize_linkedin(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    if "linkedin.com/in/" not in url:
        return None
    return url.rstrip("/")


def _canonicalize_x(url: str) -> str | None:
    url = url.strip()
    if not url:
        return None
    url = url.replace("://twitter.com/", "://x.com/")
    if "x.com/" not in url:
        return None
    return url.rstrip("/")


def load_influencers(path: Path = CSV_PATH) -> list[Influencer]:
    influencers: list[Influencer] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("Name") or "").strip()
            if not name:
                continue
            influencers.append(
                Influencer(
                    name=name,
                    role=(row.get("Role") or "").strip(),
                    company=(row.get("Company") or "").strip(),
                    linkedin_url=_canonicalize_linkedin(row.get("LinkedIn URL") or ""),
                    x_url=_canonicalize_x(row.get("X/Twitter URL") or ""),
                    why_relevant=(row.get("Why Relevant") or "").strip(),
                )
            )
    return influencers

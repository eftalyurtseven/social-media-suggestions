from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import Settings
from .models import Influencer, Post, linkedin_post_from_record, x_post_from_entry

log = logging.getLogger(__name__)

BASE_URL = "https://api.brightdata.com/datasets/v3"
POLL_INTERVAL_SECONDS = 20
POLL_TIMEOUT_SECONDS = 15 * 60
TRIGGER_MAX_RETRIES = 3


class BrightDataError(RuntimeError):
    pass


async def _trigger(
    client: httpx.AsyncClient,
    api_key: str,
    dataset_id: str,
    inputs: list[dict],
    extra_params: dict | None = None,
) -> str:
    params = {
        "dataset_id": dataset_id,
        "include_errors": "true",
    }
    if extra_params:
        params.update(extra_params)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_exc: Exception | None = None
    for attempt in range(1, TRIGGER_MAX_RETRIES + 1):
        try:
            response = await client.post(
                f"{BASE_URL}/trigger",
                params=params,
                headers=headers,
                json=inputs,
                timeout=60,
            )
            if response.status_code >= 500:
                raise BrightDataError(f"trigger 5xx: {response.status_code} {response.text}")
            if response.status_code >= 400:
                raise BrightDataError(
                    f"trigger {response.status_code}: {response.text}"
                )
            data = response.json()
            snapshot_id = data.get("snapshot_id") or data.get("id")
            if not snapshot_id:
                raise BrightDataError(f"trigger missing snapshot_id: {data}")
            log.info("triggered dataset=%s snapshot=%s", dataset_id, snapshot_id)
            return snapshot_id
        except (httpx.HTTPError, BrightDataError) as exc:
            last_exc = exc
            log.warning("trigger attempt %s/%s failed: %s", attempt, TRIGGER_MAX_RETRIES, exc)
            if attempt < TRIGGER_MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
    raise BrightDataError(f"trigger failed after {TRIGGER_MAX_RETRIES} attempts: {last_exc}")


async def _poll_until_ready(
    client: httpx.AsyncClient,
    api_key: str,
    snapshot_id: str,
) -> None:
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SECONDS
    while True:
        response = await client.get(
            f"{BASE_URL}/progress/{snapshot_id}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        status = (data.get("status") or "").lower()
        log.info("snapshot=%s status=%s", snapshot_id, status)
        if status == "ready":
            return
        if status in {"failed", "error"}:
            raise BrightDataError(f"snapshot {snapshot_id} failed: {data}")
        if asyncio.get_event_loop().time() >= deadline:
            raise BrightDataError(f"snapshot {snapshot_id} timed out (status={status})")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _fetch_snapshot(
    client: httpx.AsyncClient,
    api_key: str,
    snapshot_id: str,
) -> list[dict]:
    headers = {"Authorization": f"Bearer {api_key}"}
    response = await client.get(
        f"{BASE_URL}/snapshot/{snapshot_id}",
        params={"format": "json"},
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        for key in ("data", "results", "records"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return []
    return data if isinstance(data, list) else []


async def _run_snapshot(
    client: httpx.AsyncClient,
    api_key: str,
    dataset_id: str,
    inputs: list[dict],
    extra_params: dict | None = None,
) -> list[dict]:
    if not inputs:
        return []
    snapshot_id = await _trigger(client, api_key, dataset_id, inputs, extra_params)
    await _poll_until_ready(client, api_key, snapshot_id)
    return await _fetch_snapshot(client, api_key, snapshot_id)


def _match_influencer(
    *,
    candidate_urls: list[str],
    candidate_handles: list[str],
    influencers: list[Influencer],
    platform: str,
) -> Influencer | None:
    normalized_urls: list[str] = []
    for raw in candidate_urls:
        if not raw:
            continue
        s = str(raw).lower().rstrip("/")
        if platform == "x":
            s = s.replace("://twitter.com/", "://x.com/").replace("://mobile.x.com/", "://x.com/")
        normalized_urls.append(s)

    for inf in influencers:
        target = inf.linkedin_url if platform == "linkedin" else inf.x_url
        if not target:
            continue
        target_lc = target.lower().rstrip("/")
        for u in normalized_urls:
            if u == target_lc or target_lc in u or u in target_lc:
                return inf

    for handle in candidate_handles:
        if not handle:
            continue
        h = str(handle).strip().lstrip("@").lower()
        if not h:
            continue
        for inf in influencers:
            target = inf.linkedin_url if platform == "linkedin" else inf.x_url
            if target and f"/{h}" in target.lower():
                return inf
    return None


async def fetch_recent_posts(
    settings: Settings,
    influencers: list[Influencer],
    *,
    window_hours: int = 24,
    posts_per_profile: int = 10,
) -> tuple[list[Post], list[str]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    linkedin_inputs = [
        {"url": inf.linkedin_url} for inf in influencers if inf.linkedin_url
    ]
    x_inputs = [{"url": inf.x_url} for inf in influencers if inf.x_url]

    errors: list[str] = []

    async with httpx.AsyncClient() as client:
        linkedin_task = asyncio.create_task(
            _run_snapshot(
                client,
                settings.brightdata_api_key,
                settings.brightdata_linkedin_dataset_id,
                linkedin_inputs,
                extra_params={"type": "discover_new", "discover_by": "profile_url"},
            )
        )
        x_task = asyncio.create_task(
            _run_snapshot(
                client,
                settings.brightdata_api_key,
                settings.brightdata_x_dataset_id,
                x_inputs,
            )
        )
        linkedin_raw_result = await asyncio.gather(linkedin_task, return_exceptions=True)
        x_raw_result = await asyncio.gather(x_task, return_exceptions=True)

    linkedin_raw = linkedin_raw_result[0]
    x_raw = x_raw_result[0]

    linkedin_records: list[dict] = []
    if isinstance(linkedin_raw, Exception):
        errors.append(f"LinkedIn fetch failed: {linkedin_raw}")
        log.error("LinkedIn fetch failed: %s", linkedin_raw)
    else:
        linkedin_records = linkedin_raw

    x_records: list[dict] = []
    if isinstance(x_raw, Exception):
        errors.append(f"X fetch failed: {x_raw}")
        log.error("X fetch failed: %s", x_raw)
    else:
        x_records = x_raw

    posts: list[Post] = []

    for record in linkedin_records:
        if not isinstance(record, dict) or record.get("error"):
            continue
        discovery = record.get("discovery_input") or {}
        inf = _match_influencer(
            candidate_urls=[
                discovery.get("url") if isinstance(discovery, dict) else None,
                record.get("use_url"),
                record.get("user_url"),
            ],
            candidate_handles=[record.get("user_id"), record.get("user_name")],
            influencers=influencers,
            platform="linkedin",
        )
        if inf is None:
            continue
        post = linkedin_post_from_record(record, inf)
        if post and post.posted_at >= cutoff:
            posts.append(post)

    for record in x_records:
        if not isinstance(record, dict) or record.get("error"):
            continue
        inf = _match_influencer(
            candidate_urls=[record.get("url"), record.get("profile_url")],
            candidate_handles=[record.get("id"), record.get("profile_name")],
            influencers=influencers,
            platform="x",
        )
        if inf is None:
            continue
        for entry in record.get("posts") or []:
            if not isinstance(entry, dict):
                continue
            post = x_post_from_entry(entry, inf)
            if post and post.posted_at >= cutoff:
                posts.append(post)

    return posts, errors

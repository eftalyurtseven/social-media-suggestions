# Founder Intel Bot

Daily Slack digest of viral posts from 30 reference founder influencers on LinkedIn + X. Bot extracts patterns and drafts suggestions in Emir Atli's style for personal brand building at each::labs.

## Stack

- **Bright Data Dataset API** — LinkedIn + X scraping (anti-block, single vendor)
- **Claude Sonnet 4.6** — pattern analysis + draft generation
- **Slack incoming webhook** — delivery to a private channel
- **GitHub Actions cron** — runs daily at 14:00 UTC (≈ 06:00 PST / 07:00 PDT)
- **Python 3.12** — stateless, no DB

## Flow

```
GitHub Actions (cron 14:00 UTC)
 └─ python -m src.main
     ├─ Bright Data LinkedIn snapshot  ─┐
     ├─ Bright Data X snapshot         ─┤ parallel, then polled to ready
     ├─ filter last 24h                 │
     ├─ rank by weighted engagement     │
     ├─ Claude: patterns + 3 drafts     │
     └─ Slack: 4 sections + per-author thread
```

## Setup

### 1. Bright Data

1. Create account at [brightdata.com](https://brightdata.com)
2. Subscribe to two datasets from the marketplace:
   - **LinkedIn people posts** (by profile URL)
   - **X/Twitter posts** (by profile URL)
3. Copy each dataset ID from the dashboard
4. Generate API token from Account Settings

### 2. Slack

1. Create a private channel (e.g. `#founder-intel`)
2. Create a Slack app → enable Incoming Webhooks → install to workspace → copy the webhook URL

### 3. Anthropic

Get an API key at [console.anthropic.com](https://console.anthropic.com)

### 4. GitHub secrets

```bash
gh secret set BRIGHTDATA_API_KEY
gh secret set BRIGHTDATA_LINKEDIN_DATASET_ID
gh secret set BRIGHTDATA_X_DATASET_ID
gh secret set ANTHROPIC_API_KEY
gh secret set SLACK_WEBHOOK_URL
```

### 5. First run

```bash
gh workflow run "Daily Founder Intel Digest"
```

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in the values
set -a && source .env && set +a

# Dry run: print to stdout instead of posting
python -m src.main --dry-run

# Smoke test on one profile
python -m src.main --only "Emir Atli"
```

## Voice customization

Edit `src/prompts/draft.md` with your own posts or reference material to refine the ghostwriter voice. No code changes needed.

## Files

```
src/
  main.py            orchestrator + CLI
  config.py          env + CSV loader
  models.py          Post dataclass + normalizers
  brightdata.py      trigger → poll → fetch
  rank.py            engagement ranking
  analyze.py         Claude calls
  slack.py           Block Kit formatting
  prompts/
    analysis.md      pattern extraction
    draft.md         Emir Atli voice + draft prompt
.github/workflows/daily.yml    cron + workflow_dispatch
founder_influencers.csv        the 30 reference founders
```

## Cost (est. daily)

- Bright Data: ~$0.70 (30 profiles × 10–15 posts)
- Anthropic Sonnet 4.6: ~$0.03
- GitHub Actions: free
- **~$0.75/day (~$22/mo)**

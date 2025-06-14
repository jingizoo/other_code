#!/usr/bin/env python3
"""
Tempo × Jira — End‑to‑End Utilisation Extractor (Webhook‑aware)
==============================================================
• Pull **bulk** work‑logs from Tempo *or* accept **web‑hook* payloads
  (`eventType = worklog.*`).
• Enrich with Jira issue metadata (works with **issue key** *or* numeric
  **issue id**).
• Write `utilisation_matrix.xlsx` + raw parquet snapshots.

Run from the project root
-------------------------
```bash
export TEMPO_TOKEN=…              # Tempo → Settings → API Integration
export JIRA_EMAIL=you@corp.com
export JIRA_API_TOKEN=…           # https://id.atlassian.com → API tokens
export JIRA_SITE=mycorp.atlassian.net
python tempo_jira_utilisation.py FIN 30        # bulk, 30 days
#  ── OR ──
python tempo_jira_utilisation.py webhook events.json  # consume saved web‑hooks
```
*If your proxy re‑signs TLS, also set* `REQUESTS_CA_BUNDLE=/path/to/corp.pem`.
"""
from __future__ import annotations
import base64, json, os, sys, time
from datetime import date, timedelta
from typing import Any, Dict, Generator, List

import pandas as pd
import requests
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────── env & constants
load_dotenv()
TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE = (
    os.getenv("TEMPO_TOKEN"),
    os.getenv("JIRA_EMAIL"),
    os.getenv("JIRA_API_TOKEN"),
    os.getenv("JIRA_SITE"),
)
if not all([TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE]):
    sys.exit("❌ missing env vars – set TEMPO_TOKEN JIRA_EMAIL JIRA_API_TOKEN JIRA_SITE")
VERIFY_SSL = os.getenv("REQUESTS_CA_BUNDLE") or True

TEMPO_BASE  = "https://api.tempo.io/4"
TEMPO_HEAD  = {"Authorization": f"Bearer {TEMPO_TOKEN}", "Accept": "application/json"}
JIRA_BASE   = f"https://{JIRA_SITE}/rest/api/3"
basic       = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEAD   = {"Authorization": f"Basic {basic}", "Accept": "application/json"}

# ═══════════════════════════════════════ Tempo helpers (bulk REST v4) ═══════

def paged_get(endpoint: str, params: Dict[str, Any] | None = None, page_size: int = 100):
    offset, params = 0, params or {}
    while True:
        params.update({"offset": offset, "limit": page_size})
        r = requests.get(TEMPO_BASE + endpoint, headers=TEMPO_HEAD, params=params, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status(); data = r.json()
        yield from data.get("results", [])
        if offset + page_size >= data.get("metadata", {}).get("count", 0):
            break
        offset += page_size; time.sleep(0.2)

# ═══════════════════════════════════════ Jira helpers ═══════════════════════

def jira_project_id(key: str) -> str:
    r = requests.get(f"{JIRA_BASE}/project/{key}", headers=JIRA_HEAD, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status(); return r.json()["id"]

def jira_issue_key(issue_id: int) -> str:
    """Translate numeric issueId → key once (Jira REST)"""
    r = requests.get(f"{JIRA_BASE}/issue/{issue_id}?fields=key", headers=JIRA_HEAD, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status(); return r.json()["key"]

# ═══════════════════════════════════════ DataFrame builders ═════════════════

COL_MAP = {
    "author_displayName":       "user",
    "startDate":                "date",
    "timeSpentSeconds":         "sec",
    "billableSeconds":          "billable_sec",
    "issue_key":                "issue",       # may be NaN for web‑hook
    "issue_id":                 "issue_id",    # drv via .rename with sep="_"
    "tempoWorklogId":           "worklog_id",
    "description":              "desc",
    "attributes_account_key":   "account",
    "attributes_account_value": "account_name",
}
EXPECT = list(COL_MAP.values())


def flatten_worklogs(records: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.json_normalize(records, sep="_").rename(columns=COL_MAP)
    for col in EXPECT:
        if col not in df.columns:
            df[col] = pd.NA
    df["date"] = pd.to_datetime(df["date"])
    df["hours"] = df["sec"].astype(float) / 3600
    df["billable_hours"] = df["billable_sec"].astype(float) / 3600
    df.drop(columns=["sec", "billable_sec"], inplace=True)
    return df[EXPECT + ["hours", "billable_hours"]]

# ═══════════════════════════════════════ Jira metadata fetch ════════════════
JIRA_FIELDS = ["summary", "project", "issuetype", "labels", "components"]

def fetch_issue_meta(keys_or_ids: List[str | int]) -> pd.DataFrame:
    # Split into keys and ids
    keys = [k for k in keys_or_ids if isinstance(k, str) and k]
    ids  = [int(i) for i in keys_or_ids if isinstance(i, (int, float))]

    # 1) Resolve ids → keys (one call each, but cache locally)
    id_to_key: dict[int, str] = {}
    for iid in ids:
        try:
            id_to_key[iid] = jira_issue_key(iid)
        except requests.HTTPError:
            continue
    keys += list(id_to_key.values())

    if not keys:
        return pd.DataFrame()

    # 2) Bulk‑search by keys (100 per POST /search)
    frames: list[pd.DataFrame] = []
    for i in range(0, len(keys), 100):
        subset = keys[i : i + 100]
        payload = {"jql": f"key in ({','.join(subset)})", "fields": JIRA_FIELDS, "maxResults": 100}
        r = requests.post(f"{JIRA_BASE}/search", headers={**JIRA_HEAD, "Content-Type": "application/json"}, json=payload, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status(); frames.append(pd.json_normalize(r.json()["issues"], sep="_"))
    meta = pd.concat(frames, ignore_index=True)
    # add reverse‑lookup so we can merge even for id‑only rows
    meta["issue_id"] = meta["id"].astype(int)
    return meta

# ═══════════════════════════════════════ Enrichment & utilisation ═══════════

BUCKET_PROJECT_MAP = {"TransUnion PeopleSoft": "PeopleSoft", "Coupa": "Coupa", "OneStream": "OneStream/PS"}
ISSUE_TYPE_CAT     = {"Bug": "BAU", "Task": "BAU", "Story": "Enhancement", "Epic": "Admin"}


def enrich_and_bucket(raw_df: pd.DataFrame) -> pd.DataFrame:
    # Ensure every row has an 'issue' key (convert id → key if needed)
    need_key = raw_df[raw_df["issue"].isna() & raw_df["issue_id"].notna()].copy()
    if not need_key.empty:
        need_key["issue"] = need_key["issue_id"].apply(lambda i: jira_issue_key(int(i)))
        raw_df.loc[need_key.index, "issue"] = need_key["issue"]

    meta = fetch_issue_meta(raw_df["issue"].dropna().unique().tolist())
    meta = meta.rename(columns={
        "key": "issue",
        "fields_project_key": "project_key",
        "fields_project_name": "project_name",
        "fields_issuetype_name": "issue_type",
        "fields_labels": "labels",
        "fields_components": "components",
    })
    merged = raw_df.merge(meta, on="issue", how="left")

    merged["module"] = merged["components"].apply(lambda c: c[0]["name"] if isinstance(c, list) and c else None)
    merged["category"] = merged["issue_type"].map(ISSUE_TYPE_CAT).fillna("Other")
    merged["sub_category"] = merged["labels"].apply(lambda l: "Meetings" if isinstance(l, list) and "meeting" in l else ".")
    merged["area"] = merged["project_name"].map(BUCKET_PROJECT_MAP).fillna("Other")
    merged["week"] = merged["date"].dt.to_period("W").apply(lambda p: p.start_time.date())

    util = (
        merged.groupby(["area", "project_key", "module", "category", "sub_category", "user", "week"], as_index=False)["hours"].sum()
    )
    util["util_pct"] = (util["hours"] / 40 * 100).round(1)
    return util, merged

# ═══════════════════════════════════════ CLI entry‑point ════════════════════
if __name__ == "__main__":
    if len(sys.argv) < 3 and sys.argv[1] != "webhook":
        sys.exit("Usage: python tempo_jira_utilisation.py <PROJECT_KEY> [days_back] | webhook <events.json>")

    if sys.argv[1] == "webhook":
        events_file = Path(sys.argv[2])
        events = json.loads(events_file.read_text())
        # supports either single event or list
        payloads = [e["payload"] if "payload" in e else e for e in (events if isinstance(events, list) else [events])]
        tempo_df = flatten_worklogs(payloads)
    else:
        project_key = sys.argv[1]
        days_back   = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        logs        = list(dump_worklogs(project_key, days_back))
        tempo_df    = flatten_worklogs(logs)

    util_df, enriched = enrich_and_bucket(tempo_df)
    util_df.to_excel("utilisation_matrix.xlsx", index=False)
    enriched.to_parquet("enriched_worklogs.parquet", index=False)
    print(f"🏁 Done – rows: {len(util_df):,} → utilisation_matrix.xlsx")

#!/usr/bin/env python3
"""
Tempo × Jira — End‑to‑End Utilisation Extractor (bulk + webhook)
===============================================================
Pulls **Tempo Cloud** work‑logs in two modes
-------------------------------------------
1. *Bulk*   `python tempo_jira_utilisation.py <PROJECT_KEY> [days_back]`
   • Calls `GET /4/worklogs?project=<id>&from=…&to=…` (paged).

2. *Webhook*   `python tempo_jira_utilisation.py webhook events.json`
   • Reads saved webhook event(s) whose body looks like
     `{eventId, eventType, payload:{…single worklog…}}`.

Both paths produce:
    • **utilisation_matrix.xlsx**  (hours + util% by Area ▸ Project ▸ … ▸ Week)
    • **enriched_worklogs.parquet**  (flattened raw + Jira metadata)

Environment variables required
------------------------------
```
TEMPO_TOKEN       # Tempo → Settings → API integration token (Bearer)
JIRA_EMAIL        # Atlassian user e‑mail
JIRA_API_TOKEN    # id.atlassian.com → API tokens
JIRA_SITE         # mycorp.atlassian.net (sub‑domain only)
# Optional – CA bundle if your proxy re‑signs TLS
REQUESTS_CA_BUNDLE=/path/to/corp_root.pem
```
Add them to a `.env` file or export in your shell.
"""
from __future__ import annotations
import base64
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
from dotenv import load_dotenv

# ────────────────────────────────── 0. Environment & constants ─────────────
load_dotenv()
TEMPO_TOKEN    = os.getenv("TEMPO_TOKEN")
JIRA_EMAIL     = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_SITE      = os.getenv("JIRA_SITE")
VERIFY_SSL     = os.getenv("REQUESTS_CA_BUNDLE") or True  # can be path or bool

if not all([TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE]):
    sys.exit("❌ Set TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE env vars")

TEMPO_BASE = "https://api.tempo.io/4"
TEMPO_HEAD = {"Authorization": f"Bearer {TEMPO_TOKEN}", "Accept": "application/json"}
JIRA_BASE  = f"https://{JIRA_SITE}/rest/api/3"
BASIC_AUTH = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEAD  = {"Authorization": f"Basic {BASIC_AUTH}", "Accept": "application/json"}

# ─────────────────────────────── 1. Tempo helpers (bulk REST) ──────────────

def paged_get(endpoint: str, params: Dict[str, Any] | None = None, page_size: int = 100):
    """Stream objects from Tempo paging (`offset` / `limit`)."""
    params, offset = params or {}, 0
    while True:
        params.update({"offset": offset, "limit": page_size})
        r = requests.get(TEMPO_BASE + endpoint, headers=TEMPO_HEAD, params=params, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status(); data = r.json()
        yield from data.get("results", [])
        if offset + page_size >= data.get("metadata", {}).get("count", 0):
            break
        offset += page_size; time.sleep(0.2)


def jira_project_id(key: str) -> str:
    r = requests.get(f"{JIRA_BASE}/project/{key}", headers=JIRA_HEAD, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status(); return r.json()["id"]


def dump_worklogs(project_key: str, days_back: int = 30):
    """Return raw work‑log list for <project_key> and date window."""
    pid   = jira_project_id(project_key)
    end   = date.today()
    start = end - timedelta(days=days_back)
    logs  = list(paged_get("/worklogs", {"project": pid, "from": start.isoformat(), "to": end.isoformat()}))
    print(f"✔ Pulled {len(logs):,} work‑logs for {project_key} ({pid}) {start}→{end}")
    return logs

# ───────────────────────────── 2. Flatten Tempo JSON → DataFrame ───────────
COL_MAP = {
    "author_displayName":       "user",
    "startDate":                "date",
    "timeSpentSeconds":         "sec",
    "billableSeconds":          "billable_sec",
    "issue_key":                "issue",        # blank in web‑hook
    "issue_id":                 "issue_id",     # only when key missing
    "tempoWorklogId":           "worklog_id",
    "description":              "desc",
    "attributes_account_key":   "account",
    "attributes_account_value": "account_name",
}
EXPECT = list(COL_MAP.values())


def flatten_worklogs(records: List[Dict[str, Any]]):
    df = pd.json_normalize(records, sep="_").rename(columns=COL_MAP)
    for col in EXPECT:
        if col not in df.columns:
            df[col] = pd.NA
    df["date"] = pd.to_datetime(df["date"])
    df["hours"] = df["sec"].astype(float) / 3600
    df["billable_hours"] = df["billable_sec"].astype(float) / 3600
    df.drop(columns=["sec", "billable_sec"], inplace=True)
    return df[EXPECT + ["hours", "billable_hours"]]

# ───────────────────────────── 3. Jira metadata helpers ────────────────────
JIRA_FIELDS = ["summary", "project", "issuetype", "labels", "components"]


def jira_issue_key(issue_id: int):
    r = requests.get(f"{JIRA_BASE}/issue/{issue_id}?fields=key", headers=JIRA_HEAD, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status(); return r.json()["key"]


def fetch_issue_meta(keys_or_ids: List[str | int]):
    keys, ids = [k for k in keys_or_ids if isinstance(k, str) and k], [int(i) for i in keys_or_ids if isinstance(i, (int, float))]
    # resolve ids → keys
    for iid in ids:
        try:
            keys.append(jira_issue_key(iid))
        except requests.HTTPError:
            continue
    if not keys:
        return pd.DataFrame()
    frames = []
    for i in range(0, len(keys), 100):
        subset = keys[i : i + 100]
        payload = {"jql": f"key in ({','.join(subset)})", "fields": JIRA_FIELDS, "maxResults": 100}
        r = requests.post(f"{JIRA_BASE}/search", headers={**JIRA_HEAD, "Content-Type": "application/json"}, json=payload, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status(); frames.append(pd.json_normalize(r.json()["issues"], sep="_"))
    meta = pd.concat(frames, ignore_index=True)
    meta["issue_id"] = meta["id"].astype(int)
    return meta

# ───────────────────────────── 4. Enrichment & utilisation bucket ──────────
PROJECT_AREA = {"TransUnion PeopleSoft": "PeopleSoft", "Coupa": "Coupa", "OneStream": "OneStream/PS"}
ISSUE_CAT    = {"Bug": "BAU", "Task": "BAU", "Story": "Enhancement", "Epic": "Admin"}


def enrich_and_utilise(raw_df: pd.DataFrame):
    # Ensure every row has an issue key
    need_key = raw_df[raw_df["issue"].isna() & raw_df["issue_id"].notna()]
    if not need_key.empty:
        raw_df.loc[need_key.index, "issue"] = need_key["issue_id"].apply(lambda i: jira_issue_key(int(i)))

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
    merged["category"] = merged["issue_type"].map(ISSUE_CAT).fillna("Other")
    merged["sub_category"] = merged["labels"].apply(lambda l: "Meetings" if isinstance(l, list) and "meeting" in l else ".")
    merged["area"] = merged["project_name"].map(PROJECT_AREA).fillna("Other")
    merged["week"] = merged["date"].dt.to_period("W").apply(lambda p: p.start_time.date())

    util = (
        merged.groupby(["area", "project_key", "module", "category", "sub_category", "user", "week"], as_index=False)["hours"].sum()
    )
    util["util_pct"] = (util["hours"] / 40 * 100).round(1)
    return util, merged

# ───────────────────────────── 5. CLI entry‑point ──────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(
            "Usage:
  python tempo_jira_utilisation.py <PROJECT_KEY> [days_back]
  python tempo_jira_utilisation.py webhook <events.json>"
        )

    mode = sys.argv[1]
    if mode == "webhook":
        if len(sys.argv) != 3:
            sys.exit("Provide the webhook JSON file: webhook <events.json>")
        events = json.loads(Path(sys.argv[2]).read_text())
        payloads = [e["payload"] if "payload" in e else e for e in (events if isinstance(events, list) else [events])]
        tempo_df = flatten_worklogs(payloads)
    else:
        project_key = mode
        days_back   = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        tempo_df    = flatten_worklogs(dump_worklogs(project_key, days_back))

    util_df, enriched = enrich_and_utilise(tempo_df)
    util_df.to_excel("utilisation_matrix.xlsx", index=False)
    enriched.to_parquet("enriched_worklogs.parquet", index=False)
    print(f"🏁  Done – {len(util_df):,} utilisation rows → utilisation_matrix.xlsx")

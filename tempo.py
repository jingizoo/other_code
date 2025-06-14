#!/usr/bin/env python3
"""
Tempo × Jira — End‑to‑End Utilisation Extractor
==============================================
Pulls work‑logs from Tempo Cloud, enriches them with Jira issue metadata and
writes `utilisation_matrix.xlsx`.

Usage (from project root)
-------------------------
export TEMPO_TOKEN=…      # Tempo ➜ Settings ➜ API integration ➜ token
export JIRA_EMAIL=…       # Atlassian account email
export JIRA_API_TOKEN=…   # id.atlassian.com ➜ API tokens
export JIRA_SITE=mycorp.atlassian.net
python tempo_jira_utilisation.py FIN 30
"""
from __future__ import annotations
import base64, os, sys, time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List

import pandas as pd
import requests
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# 0.  Environment
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

TEMPO_TOKEN    = os.getenv("TEMPO_TOKEN")
JIRA_EMAIL     = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_SITE      = os.getenv("JIRA_SITE")               # mycorp.atlassian.net

if not all([TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE]):
    sys.exit("❌  Missing one of TEMPO_TOKEN / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_SITE")

VERIFY_SSL = os.getenv("REQUESTS_CA_BUNDLE") or True

TEMPO_BASE    = "https://api.tempo.io/4"
TEMPO_HEADERS = {"Authorization": f"Bearer {TEMPO_TOKEN}", "Accept": "application/json"}

basic         = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEADERS  = {"Authorization": f"Basic {basic}", "Accept": "application/json"}
JIRA_BASE     = f"https://{JIRA_SITE}/rest/api/3"

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Tempo paginator
# ─────────────────────────────────────────────────────────────────────────────

def paged_get(endpoint: str, params: Dict[str, Any] | None = None, page_size: int = 100) -> Generator[Dict[str, Any], None, None]:
    offset = 0
    params = params or {}
    while True:
        params.update({"offset": offset, "limit": page_size})
        r = requests.get(TEMPO_BASE + endpoint, headers=TEMPO_HEADERS, params=params, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status()
        payload = r.json()
        yield from payload.get("results", [])
        if offset + page_size >= payload.get("metadata", {}).get("count", 0):
            break
        offset += page_size
        time.sleep(0.2)

# ─────────────────────────────────────────────────────────────────────────────
# 2.  Jira helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_project_id(key: str) -> str:
    r = requests.get(f"{JIRA_BASE}/project/{key}", headers=JIRA_HEADERS, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json()["id"]

# ─────────────────────────────────────────────────────────────────────────────
# 3.  Tempo extractor
# ─────────────────────────────────────────────────────────────────────────────

def dump_worklogs(project_key: str, days_back: int = 30):
    pid   = get_project_id(project_key)
    end   = date.today()
    start = end - timedelta(days=days_back)
    logs  = list(paged_get("/worklogs", {"project": pid, "from": start.isoformat(), "to": end.isoformat()}))
    print(f"✔ Pulled {len(logs):,} work‑logs for {project_key} ({pid}) {start}→{end}")
    return logs

# ─────────────────────────────────────────────────────────────────────────────
# 4.  Flatten Tempo JSON ➜ DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def to_dataframe(worklogs: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.json_normalize(worklogs, sep="_")
    cols = {
        "author_displayName":       "user",
        "startDate":                "date",
        "timeSpentSeconds":         "sec",
        "billableSeconds":          "billable_sec",
        "issue_key":                "issue",
        "tempoWorklogId":           "worklog_id",
        "description":              "desc",
        "attributes_account_key":   "account",
        "attributes_account_value": "account_name",
    }
    df = df.rename(columns=cols)
    expected = list(cols.values())
    for c in expected:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[expected]
    df["date"]           = pd.to_datetime(df["date"])
    df["hours"]          = df["sec"] / 3600
    df["billable_hours"] = df["billable_sec"] / 3600
    df.drop(columns=["sec", "billable_sec"], inplace=True)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# 5.  Jira metadata fetch (robust to NA keys)
# ─────────────────────────────────────────────────────────────────────────────
JIRA_FIELDS = ["summary", "project", "issuetype", "labels", "components"]

def fetch_issues_metadata(issue_keys: List[str]) -> pd.DataFrame:
    clean_keys = [str(k) for k in issue_keys if pd.notna(k)]
    if not clean_keys:
        return pd.DataFrame()
    batch_size = 100
    frames: List[pd.DataFrame] = []
    for i in range(0, len(clean_keys), batch_size):
        keys = clean_keys[i:i + batch_size]
        jql  = f"key in ({','.join(keys)})"
        payload = {"jql": jql, "fields": JIRA_FIELDS, "maxResults": batch_size}
        r = requests.post(f"{JIRA_BASE}/search", headers={**JIRA_HEADERS, "Content-Type": "application/json"}, json=payload, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status()
        frames.append(pd.json_normalize(r.json()["issues"], sep="_"))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# 6.  Enrich & bucket
# ─────────────────────────────────────────────────────────────────────────────

def build_enriched_df(tempo_df: pd.DataFrame) -> pd.DataFrame:
    meta = fetch_issues_metadata(tempo_df["issue"].unique().tolist())
    meta = meta.rename(columns={
        "key": "issue",
        "fields_project_key":       "project_key",
        "fields_project_name":      "project_name",
        "fields_issuetype_name":    "issue_type",
        "fields_labels":            "labels",
        "fields_components":        "components",
    })
    merged = tempo_df.merge(meta, on="issue", how="left")
    merged["module"] = merged["components"].apply(lambda c: c[0]["name"] if isinstance(c, list) and c else None)
    merged["category"] = merged["issue_type"].map({"Bug": "BAU", "Task": "BAU", "Story": "Enhancement", "Epic": "Admin"}).fillna("Other")
    merged["sub_category"] = merged["labels"].apply(lambda l: "Meetings" if isinstance(l, list) and "meeting" in l else ".")
    merged["area"] = merged["project_name"].map({"TransUnion PeopleSoft": "PeopleSoft", "Coupa": "Coupa", "OneStream": "OneStream/PS"}).fillna("Other")
    return merged

# ─────────────────────────────────────────────────────────────────────────────
# 7.  Utilisation matrix
# ─────────────────────────────────────────────────────────────────────────────

def build_utilisation(enriched: pd.DataFrame, weekly_capacity: int = 40) -> pd.DataFrame:
    enriched["week"] = enriched["date"].dt.to_period("W").apply(lambda p: p.start_time.date())
    hours = enriched.groupby(["area", "project_key", "module", "category", "sub_category", "user", "week"], as_index=False)["hours"].sum()
    hours["util_pct"] = (hours["hours"] / weekly_capacity * 100).round(1)
    return hours

# ─────────────────────────────────────────────────────────────────────────────
# 8.  Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python tempo_jira_utilisation.py <PROJECT_KEY> [days_back]")
    project_key = sys.argv[1]
    days_back   = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    logs       = dump_worklogs(project_key, days_back)
    tempo_df   = to_dataframe(logs)
    enriched   = build_enriched_df(tempo

#!/usr/bin/env python3
"""
Tempo × Jira ― End‑to‑End Utilisation Extractor
================================================
Pulls work‑logs from Tempo Cloud, enriches them with Jira issue metadata, and
produces a tidy utilisation matrix that you can feed straight into Excel / BI.

💾  Outputs
-----------
    • utilisation_matrix.xlsx  – hours per (Area ▸ Project ▸ Module ▸ Category ▸
      Sub‑category ▸ User ▸ Week)
    • raw_worklogs.parquet     – the flattened Tempo payload (optional)

🚀  Usage
---------
    export TEMPO_TOKEN=xxxxx              # Bearer from Tempo “API Integration”
    export JIRA_EMAIL=you@corp.com        # Atlassian account e‑mail
    export JIRA_API_TOKEN=yyyyy           # Create at id.atlassian.com → API tokens
    export JIRA_SITE=mycorp.atlassian.net # <site>.atlassian.net (no protocol)

    # optional – point Python Requests at your corporate root cert
    # export REQUESTS_CA_BUNDLE=/etc/ssl/certs/corp_root.pem

    python tempo_jira_utilisation.py FIN 30   # FIN = project KEY, 30 days back

The first argument is the **Jira project key** (e.g. FIN); the second argument
is the number of days to pull (default 30).
"""

from __future__ import annotations
import base64
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List

import pandas as pd
import requests
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# 0.  Environment & constants
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()

TEMPO_TOKEN   = os.getenv("TEMPO_TOKEN")
JIRA_EMAIL    = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN= os.getenv("JIRA_API_TOKEN")
JIRA_SITE     = os.getenv("JIRA_SITE")                   # e.g. mycorp.atlassian.net

if not all([TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE]):
    sys.exit("❌  Set TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE env vars")

CA_BUNDLE   = os.getenv("REQUESTS_CA_BUNDLE")            # optional
VERIFY_SSL  = CA_BUNDLE if CA_BUNDLE else True            # or False (not advised!)

TEMPO_BASE = "https://api.tempo.io/4"
TEMPO_HEADERS = {
    "Authorization": f"Bearer {TEMPO_TOKEN}",
    "Accept": "application/json",
}

basic = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEADERS = {
    "Authorization": f"Basic {basic}",
    "Accept": "application/json",
}
JIRA_BASE = f"https://{JIRA_SITE}/rest/api/3"


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Generic Tempo pager
# ─────────────────────────────────────────────────────────────────────────────

def paged_get(endpoint: str,
              params: Dict[str, Any] | None = None,
              page_size: int = 100) -> Generator[Dict[str, Any], None, None]:
    offset = 0
    params = params or {}
    while True:
        params.update({"offset": offset, "limit": page_size})
        r = requests.get(
            TEMPO_BASE + endpoint,
            headers=TEMPO_HEADERS,
            params=params,
            timeout=30,
            verify=VERIFY_SSL,
        )
        r.raise_for_status()
        payload = r.json()
        yield from payload.get("results", [])
        if offset + page_size >= payload.get("metadata", {}).get("count", 0):
            break
        offset += page_size
        time.sleep(0.2)  # be kind to API limits


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Jira helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_project_id(project_key: str) -> str:
    """Translate a Jira project KEY (e.g. FIN) into its numeric projectId."""
    url = f"{JIRA_BASE}/project/{project_key}"
    r = requests.get(url, headers=JIRA_HEADERS, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json()["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Tempo extractor
# ─────────────────────────────────────────────────────────────────────────────

def dump_worklogs(project_key: str, days_back: int = 30) -> List[Dict[str, Any]]:
    pid   = get_project_id(project_key)
    end   = date.today()
    start = end - timedelta(days=days_back)

    params = {
        "project": pid,            # numeric ID required in v4
        "from":    start.isoformat(),
        "to":      end.isoformat(),
    }

    worklogs = list(paged_get("/worklogs", params=params))
    print(f"✔︎  Pulled {len(worklogs):,} work‑logs for {project_key} ({pid}) "
          f"{start} → {end}")
    return worklogs


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Flatten Tempo JSON ➜ DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def to_dataframe(worklogs: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.json_normalize(worklogs, sep="_")

    cols = {
        "author_displayName":        "user",
        "startDate":                 "date",
        "timeSpentSeconds":          "sec",
        "billableSeconds":           "billable_sec",
        "issue_key":                 "issue",
        "tempoWorklogId":            "worklog_id",
        "description":               "desc",
        "attributes_account_key":    "account",
        "attributes_account_value":  "account_name",
    }

    df = df.rename(columns=cols)[list(cols.values())]

    df["date"]           = pd.to_datetime(df["date"])
    df["hours"]          = df["sec"] / 3600
    df["billable_hours"] = df["billable_sec"] / 3600
    df.drop(columns=["sec", "billable_sec"], inplace=True)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Bulk Jira issue metadata fetch
# ─────────────────────────────────────────────────────────────────────────────
JIRA_FIELDS = [
    "summary",
    "project",
    "issuetype",
    "labels",
    "components",
    # add your custom fields below, e.g. "customfield_12345"
]

def fetch_issues_metadata(issue_keys: List[str]) -> pd.DataFrame:
    batch_size = 100
    frames: List[pd.DataFrame] = []

    for i in range(0, len(issue_keys), batch_size):
        keys = issue_keys[i: i + batch_size]
        jql  = f"key in ({','.join(keys)})"

        payload = {"jql": jql, "fields": JIRA_FIELDS, "maxResults": batch_size}

        r = requests.post(
            f"{JIRA_BASE}/search",
            headers={**JIRA_HEADERS, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
            verify=VERIFY_SSL,
        )
        r.raise_for_status()
        issues = r.json()["issues"]
        f = pd.json_normalize(issues, sep="_")
        frames.append(f)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 6.  Join & derive business buckets
# ─────────────────────────────────────────────────────────────────────────────

def build_enriched_df(tempo_df: pd.DataFrame) -> pd.DataFrame:
    issue_keys = tempo_df["issue"].unique().tolist()
    meta_df    = fetch_issues_metadata(issue_keys)

    meta_df = meta_df.rename(columns={
        "key": "issue",
        "fields_project_key":        "project_key",
        "fields_project_name":       "project_name",
        "fields_issuetype_name":     "issue_type",
        "fields_labels":             "labels",
        "fields_components":         "components",
    })

    merged = tempo_df.merge(meta_df, on="issue", how="left")

    # Derive Module from first component or drop‑in custom field
    merged["module"] = merged["components"].apply(
        lambda x: x[0]["name"] if isinstance(x, list) and x else None
    )

    # Category mapping by Issue Type
    merged["category"] = merged["issue_type"].map({
        "Bug":      "BAU",
        "Task":     "BAU",
        "Story":    "Enhancement",
        "Epic":     "Admin",
    }).fillna("Other")

    # Sub‑category from label presence
    merged["sub_category"] = merged["labels"].apply(
        lambda lbls: "Meetings" if isinstance(lbls, list) and "meeting" in lbls else "."
    )

    # Area – coarse mapping by project name
    merged["area"] = merged["project_name"].map({
        "TransUnion PeopleSoft": "PeopleSoft",
        "Coupa":                 "Coupa",
        "OneStream":             "OneStream/PS",
    }).fillna("Other")

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# 7.  Utilisation matrix builder
# ─────────────────────────────────────────────────────────────────────────────

def build_utilisation(enriched: pd.DataFrame, capacity_per_week: int = 40) -> pd.DataFrame:
    enriched["week"] = enriched["date"].dt.to_period("W").apply(lambda p: p.start_time.date())

    hours = (
        enriched.groupby(
            ["area", "project_key", "module", "category", "sub_category", "user", "week"],
            as_index=False,
        )["hours"].sum()
    )

    hours["util_pct"] = (hours["hours"] / capacity_per_week * 100).round(1)
    return hours


# ─────────────────────────────────────────────────────────────────────────────
# 8.  Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # cmd‑line args: project key, days_back
    if len(sys.argv) < 2:
        sys.exit("Usage: python tempo_jira_utilisation.py <PROJECT_KEY> [days_back]")

    PROJECT_KEY = sys.argv[1]
    DAYS_BACK   = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    worklogs   = dump_worklogs(PROJECT_KEY, days_back=DAYS_BACK)
    tempo_df   = to_dataframe(worklogs)
    enriched   = build_enriched_df(tempo_df)
    util_df    = build_utilisation(enriched)

    # Persist
    util_df.to_excel("utilisation_matrix.xlsx", index=False)
    Path("raw_worklogs.parquet").write_bytes(tempo_df.to_parquet())

    print("✅  utilisation_matrix.xlsx written (", len(util_df), "rows )")

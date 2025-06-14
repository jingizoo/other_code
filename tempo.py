#!/usr/bin/env python3
"""
Tempo × Jira — One‑file Utilisation Extractor
=============================================
Works for **both** Tempo REST (bulk) *and* Tempo web‑hook JSON.  Pulls Jira
metadata directly from the `issue.self` URL inside every work‑log, so no JQL
searches or id→key conversions needed.

Usage
-----
```bash
# env vars (put in .env or export in the shell)
TEMPO_TOKEN=…      # Tempo → Settings → API integration token (Bearer)
JIRA_EMAIL=…       # Atlassian account e‑mail
JIRA_API_TOKEN=…   # https://id.atlassian.com → API tokens
JIRA_SITE=mycorp.atlassian.net

python tempo_jira_utilisation.py FIN 30           # bulk pull (30 days)
python tempo_jira_utilisation.py webhook events.json  # parse web‑hook file
```
Outputs
-------
• **utilisation_matrix.xlsx** – hours + util% per Area ▸ Project ▸ Module ▸ Week
• **enriched_worklogs.parquet** – flattened work‑logs + Jira fields (for audit)
"""
from __future__ import annotations
import base64, json, os, sys, time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
from dotenv import load_dotenv

# ───────────────────────── 0 · ENV & CONSTANTS ──────────────────────────────
load_dotenv()
REQ = ["TEMPO_TOKEN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_SITE"]
missing = [v for v in REQ if not os.getenv(v)]
if missing:
    sys.exit(f"❌ Missing env vars: {', '.join(missing)}")
TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE = (os.getenv(k) for k in REQ)
VERIFY_SSL = os.getenv("REQUESTS_CA_BUNDLE") or True   # may be a cert path

TEMPO_BASE = "https://api.tempo.io/4"
TEMPO_HEAD = {"Authorization": f"Bearer {TEMPO_TOKEN}", "Accept": "application/json"}

JIRA_BASE  = f"https://{JIRA_SITE}/rest/api/3"
BASIC      = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEAD  = {"Authorization": f"Basic {BASIC}", "Accept": "application/json"}

# ───────────────────────── 1 · TEMPO HELPERS ────────────────────────────────

def paged_get(endpoint: str, params: Dict[str, Any] | None = None, page: int = 100):
    params, offset = params or {}, 0
    while True:
        params.update({"offset": offset, "limit": page})
        r = requests.get(f"{TEMPO_BASE}{endpoint}", headers=TEMPO_HEAD, params=params, timeout=30, verify=VERIFY_SSL)
        r.raise_for_status(); data = r.json()
        yield from data.get("results", [])
        if offset + page >= data.get("metadata", {}).get("count", 0):
            break
        offset += page; time.sleep(0.2)

def jira_project_id(key: str) -> str:
    r = requests.get(f"{JIRA_BASE}/project/{key}", headers=JIRA_HEAD, timeout=30, verify=VERIFY_SSL)
    r.raise_for_status(); return r.json()["id"]

def pull_worklogs(project_key: str, days_back: int):
    pid   = jira_project_id(project_key)
    end   = date.today(); start = end - timedelta(days=days_back)
    logs  = list(paged_get("/worklogs", {"project": pid, "from": start.isoformat(), "to": end.isoformat()}))
    print(f"[INFO] pulled {len(logs):,} work‑logs from Tempo for {project_key}")
    return logs

# ───────────────────────── 2 · FLATTEN TEMPO JSON ───────────────────────────
COL_MAP = {
    "author.displayName": "user",
    "author.accountId":   "user_id",   # fallback when displayName missing
    "startDate":          "date",
    "timeSpentSeconds":   "sec",
    "billableSeconds":    "billable_sec",
    "issue.self":         "issue_url",   # holds the REST link
    "issue.id":           "issue_id",    # numeric id (bulk & webhook)
    "tempoWorklogId":     "worklog_id",
    "description":        "desc",
}
EXPECT = list(COL_MAP.values())

def flatten_worklogs(records: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.json_normalize(records).rename(columns=COL_MAP)
    for c in EXPECT:
        df[c] = df.get(c, pd.NA)
    # displayName fallback
    df["user"] = df["user"].fillna(df["user_id"])
    df.drop(columns="user_id", inplace=True, errors="ignore")
    # metrics
    df["hours"]          = df.get("sec", pd.Series(dtype=float)) / 3600
    df["billable_hours"] = df.get("billable_sec", pd.Series(dtype=float)) / 3600
    df["date"] = pd.to_datetime(df["date"])
    keep = [c for c in EXPECT if c in df.columns]
    out  = df[keep + ["hours", "billable_hours"]]
    print(f"[DEBUG] after flatten → {len(out)} rows")
    return out

# ───────────────────────── 3 · JIRA META VIA issue.self (NEW) ───────────────

def meta_from_urls(urls: List[str]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for url in urls:
        try:
            r = requests.get(f"{url}?fields=key,project,issuetype,labels,components", headers=JIRA_HEAD, timeout=20, verify=VERIFY_SSL)
            r.raise_for_status(); j = r.json(); f = j["fields"]
            rows.append({
                "issue_id":     int(j["id"]),
                "issue":        j["key"],
                "project_key":  f["project"]["key"],
                "project_name": f["project"]["name"],
                "issue_type":   f["issuetype"]["name"],
                "labels":       f["labels"],
                "components":   f["components"],
            })
        except requests.HTTPError:
            continue
    meta_df = pd.DataFrame(rows)
    print(f"[DEBUG] Jira meta rows: {len(meta_df)} (via self URLs)")
    return meta_df

# ───────────────────────── 4 · ENRICH & UTILISE ─────────────────────────────
ISSUE_CAT = {"Bug": "BAU", "Task": "BAU", "Story": "Enhancement", "Epic": "Admin"}
AREA_MAP  = {"TransUnion PeopleSoft": "PeopleSoft", "Coupa": "Coupa", "OneStream": "OneStream/PS"}

def enrich_and_utilise(df: pd.DataFrame):
    meta = meta_from_urls(df["issue_url"].dropna().unique().tolist())
    df["issue_id"] = df["issue_id"].astype("Int64")
    meta["issue_id"] = meta["issue_id"].astype("Int64")
    merged = df.merge(meta, on="issue_id", how="left")
    print(f"[DEBUG] after merge → {len(merged)} rows")

    merged["module"] = merged["components"].apply(lambda c: c[0]["name"] if isinstance(c, list) and c else "Unknown")
    merged["category"] = merged["issue_type"].map(ISSUE_CAT).fillna("Unknown")
    merged["sub_category"] = merged["labels"].apply(lambda l: "Meetings" if isinstance(l, list) and "meeting" in l else "Unknown")
    merged["area"] = merged["project_name"].map(AREA_MAP).fillna("Unknown")
    merged["week"] = merged["date"].dt.to_period("W").apply(lambda p: p.start_time.date())

    util = merged.groupby(["area", "project_key", "module", "category", "sub_category", "user", "week"], as_index=False)["hours"].sum()
    util["util_pct"] = (util["hours"] / 40 * 100).round(1)
    print(f"[DEBUG] util rows → {len(util)}")
    return util, merged

# ───────────────────────── 5 · CLI ENTRY ────────────────────────────────────
if __name__ == "__main__":
    print("[DEBUG] argv →", sys.argv)   # ADDED: show raw CLI args early
    if len(sys.argv) < 2:
        sys.exit(
            "Usage: python tempo_jira_utilisation.py <PROJECT_KEY> [days_back] | "
            "webhook <file.json>"
        )

    mode = sys.argv[1]
    if mode == "webhook":
        if len(sys.argv) != 3:
            sys.exit("Provide the webhook JSON file: webhook <file.json>")
        events = json.loads(Path(sys.argv[2]).read_text())
        payloads = [e.get("payload", e) for e in (events if isinstance(events, list) else [events])]
        df_flat = flatten_worklogs(payloads)
    else:
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        df_flat = flatten_worklogs(pull_worklogs(mode, days))

    util_df, enriched = enrich_and_utilise(df_flat)

    util_df.to_excel("utilisation_matrix.xlsx", index=False)
    enriched.to_parquet("enriched_worklogs.parquet", index=False)
    print("🏁 done – wrote utilisation_matrix.xlsx (rows:", len(util_df), ")")

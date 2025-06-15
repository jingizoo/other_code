#!/usr/bin/env python3
"""
Tempo × Jira — Utilisation Extractor v3
======================================
* Fixes accountId→displayName resolution
* Treats **labels** array intelligently → `category` / `sub_category`
* Uses Tempo’s correct query parameter **`projectId`**

Label‑to‑bucket logic
---------------------
| Primary label match  | category   | sub_category |
|----------------------|------------|--------------|
| `enhancement`        | Enhancement| .            |
| `bau`                | BAU        | .            |
| `audit`              | Admin      | Audit        |
| `meeting`            | Admin      | Meeting      |
| `holiday` / `vacation`| Vacation   | Vacation     |
| (none of above)      | Unknown    | Unknown      |

Any label list is lower‑cased before matching; first hit wins.
"""
from __future__ import annotations
import base64, json, os, sys, time
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
from dotenv import load_dotenv

# ───────────────────────── 0 · ENV & CONSTANTS ─────────────────────────────
load_dotenv()
REQ = ["TEMPO_TOKEN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_SITE"]
missing = [v for v in REQ if not os.getenv(v)]
if missing:
    sys.exit(f"❌ missing env vars: {', '.join(missing)}")
TEMPO_TOKEN, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_SITE = (os.getenv(k) for k in REQ)
VERIFY_SSL = os.getenv("REQUESTS_CA_BUNDLE") or True

TEMPO_BASE = "https://api.tempo.io/4"
TEMPO_HEAD = {"Authorization": f"Bearer {TEMPO_TOKEN}", "Accept": "application/json"}

JIRA_BASE  = f"https://{JIRA_SITE}/rest/api/3"
BASIC      = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
JIRA_HEAD  = {"Authorization": f"Basic {BASIC}", "Accept": "application/json"}

# ───────────────────────── 1 · TEMPO HELPERS ───────────────────────────────

def paged_get(endpoint: str, params: Dict[str, Any] | None = None, page: int = 1000):
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
    logs  = list(paged_get("/worklogs", {"projectId": pid,  # CHANGED
                                         "from": start.isoformat(),
                                         "to":   end.isoformat()}))
    print(f"[INFO] pulled {len(logs):,} work‑logs for {project_key}")
    return logs

# ───────────────────────── 2 · ACCOUNT ID → NAME ───────────────────────────
@lru_cache(maxsize=2048)
def account_id_to_name(acc: str) -> str | None:
    try:
        r = requests.get(f"{JIRA_BASE}/user", headers=JIRA_HEAD, params={"accountId": acc}, timeout=20, verify=VERIFY_SSL)
        r.raise_for_status(); return r.json().get("displayName")
    except requests.HTTPError:
        return None

# ───────────────────────── 3 · FLATTEN TEMPO JSON ──────────────────────────
COL_MAP = {
    "author.displayName": "user",
    "author.accountId":   "user_id",
    "startDate":          "date",
    "timeSpentSeconds":   "sec",
    "billableSeconds":    "billable_sec",
    "issue.self":         "issue_url",
    "issue.id":           "issue_id",
    "tempoWorklogId":     "worklog_id",
    "description":        "desc",
}
EXPECT = list(COL_MAP.values())

def flatten(records: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.json_normalize(records).rename(columns=COL_MAP)
    for c in EXPECT:
        df[c] = df.get(c, pd.NA)
    # resolve user name
    def _resolve_user(row):
        if pd.notna(row["user"]) and str(row["user"]).strip():
            return row["user"]
        if pd.notna(row.get("user_id")):
            name = account_id_to_name(str(row["user_id"]))
            if name:
                return name
            return row["user_id"]
        return "Unknown"

    df["user"] = df.apply(_resolve_user, axis=1)
    df.drop(columns="user_id", inplace=True, errors="ignore")
    df["hours"]          = df.get("sec", pd.Series(dtype=float)) / 3600
    df["billable_hours"] = df.get("billable_sec", pd.Series(dtype=float)) / 3600
    df["date"] = pd.to_datetime(df["date"])
    keep = [c for c in EXPECT if c in df.columns]
    return df[keep + ["hours", "billable_hours"]]

# ───────────────────────── 4 · JIRA META VIA issue.self ─────────────────────

def meta_from_urls(urls: List[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for url in urls:
        try:
            r = requests.get(f"{url}?fields=key,project,issuetype,labels,components,status,summary", headers=JIRA_HEAD, timeout=20, verify=VERIFY_SSL)
            r.raise_for_status(); d = r.json(); f = d["fields"]
            rows.append({
                "issue_id":     int(d["id"]),
                "issue":        d["key"],
                "project_key":  f["project"]["key"],
                "project_name": f["project"]["name"],
                "issue_type":   f["issuetype"]["name"],
                "labels":       f["labels"],
                "components":   f["components"],
                "summary":      f.get("summary", ""),
                "status":       f.get("status", {}).get("name"),
            })
        except requests.HTTPError:
            continue
    return pd.DataFrame(rows)

# ───────────────────────── 5 · LABEL BUCKET RULES ───────────────────────────

def label_to_buckets(labels: list[str] | None) -> tuple[str, str]:
    if not isinstance(labels, list):
        return "Unknown", "Unknown"
    lset = {l.lower() for l in labels}
    if any("enhancement" in l for l in lset):
        return "Enhancement", "."
    if any("bau" in l for l in lset):
        return "BAU", "."
    if any("audit" in l for l in lset):
        return "Admin", "Audit"
    if any("meeting" in l for l in lset):
        return "Admin", "Meeting"
    if any(l in {"holiday", "vacation"} for l in lset):
        return "Vacation", "Vacation"
    return "Unknown", "Unknown"

AREA_MAP = {"TransUnion PeopleSoft": "PeopleSoft", "Coupa": "Coupa", "OneStream": "OneStream/PS"}

from functools import lru_cache

@lru_cache(maxsize=1024)
def account_id_to_name(account_id: str) -> str | None:
    """
    Convert an Atlassian accountId to a display name.
    Caches results so we hit the /user endpoint once per id.
    """
    try:
        r = requests.get(
            f"{JIRA_BASE}/user",
            headers=JIRA_HEAD,
            params={"accountId": account_id},
            timeout=20,
            verify=VERIFY_SSL,
        )
        r.raise_for_status()
        return r.json().get("displayName")
    except requests.HTTPError:
        return None

# ───────────────────────── 6 · ENRICH & UTILISE ─────────────────────────────

def enrich(df_flat: pd.DataFrame):
    meta = meta_from_urls(df_flat["issue_url"].dropna().unique().tolist())
    meta["issue_id"] = meta["issue_id"].astype("Int64")
    df_flat["issue_id"] = df_flat["issue_id"].astype("Int64")
    merged = df_flat.merge(meta, on="issue_id", how="left")

    # Team filter
    tf = os.getenv("TEAM_FILTER")
    if tf:
        merged = merged[merged["project_key"].str.contains(tf, na=False)]

    merged["module"] = merged["components"].apply(lambda c: c[0]["name"] if isinstance(c, list) and c else "Unknown")
    merged["area"] = merged["project_name"].map(AREA_MAP).fillna("Unknown")
    merged[["category", "sub_category"]] = merged.apply(lambda r: pd.Series(label_to_buckets(r["labels"])), axis=1)
    merged["week"] = merged["date"].dt.to_period("W").apply(lambda p: p.start_time.date())

    # final utilisation aggregations
    util = (
        merged.groupby(["area", "project_key", "module", "category", "sub_category", "user", "week"], as_index=False)["hours"].sum()
    )
    util["util_pct"] = (util["hours"] / 40 * 100).round(1)
    return util, merged

# ───────────────────────── 7 · MAIN ─────────────────────────────────────────
if __name__ == "__main__":
    print("[DEBUG] argv →", sys.argv)
    if len(sys.argv) < 2:
        sys.exit("Usage: python tempo_jira_utilisation.py <PROJECT_KEY> [days_back] | webhook <file.json>")

    mode = sys.argv[1]
    if mode == "webhook":
        if len(sys.argv) != 3:
            sys.exit("Provide the webhook JSON file: webhook <file.json>")
        events = json.loads(Path(sys.argv[2]).read_text())
        payloads = [e.get("payload", e) for e in (events if isinstance(events, list) else [events])]
        df_flat = flatten(payloads)
    else:
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7  # default last week
        df_flat = flatten(pull_worklogs(mode, days))

    util_df, enriched_df = enrich(df_flat)

    # write Excel with auto‑width for better readability
    excel_engine = None
    for eng in ("xlsxwriter", "openpyxl"):
        try:
            __import__(eng)
            excel_engine = eng
            break
        except ModuleNotFoundError:
            continue
    if not excel_engine:
        sys.exit("❌  Install 'xlsxwriter' or 'openpyxl' to create Excel files.")

    with pd.ExcelWriter("utilisation_matrix.xlsx", engine=excel_engine) as xl:
        util_df.to_excel(xl, sheet_name="Raw", index=False)
        pivot_df = util_df.pivot_table(
            index=["area", "project_key", "module", "user"],
            columns="week", values="hours", aggfunc="sum", fill_value=0,
        )
        pivot_df.to_excel(xl, sheet_name="Pivot")

        # auto‑width only when xlsxwriter is active
        if excel_engine == "xlsxwriter":
            def autofit(ws, dataframe):
                for idx, col in enumerate(dataframe.columns, start=0):
                    series = dataframe[col].astype(str)
                    maxlen = max(series.map(len).max(), len(str(col))) + 2
                    ws.set_column(idx, idx, maxlen)
            autofit(xl.sheets["Raw"], util_df)
            autofit(xl.sheets["Pivot"], pivot_df)

    enriched_df.to_parquet("enriched_worklogs.parquet", index=False)
    print(f"🏁 done – {len(util_df):,} rows → utilisation_matrix.xlsx")

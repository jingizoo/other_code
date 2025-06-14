#!/usr/bin/env python3
"""
Quick-start script to pull data from the Tempo Cloud REST API.

Prereqs
-------
pip install requests python-dotenv
Create a .env file in the same folder with
    TEMPO_TOKEN=<paste-your-token-here>
"""

import os
import sys
import time
from datetime import date, timedelta
from typing import Generator, Dict, Any, List

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# 0.  House-keeping – load token & set constants
# ---------------------------------------------------------------------------
load_dotenv()                                               # reads .env
TOKEN = os.getenv("TEMPO_TOKEN")
if not TOKEN:
    sys.exit("❌  TEMPO_TOKEN is missing – set it in the environment or .env")

BASE_URL = "https://api.tempo.io/4"                         # v4 is current
HEADERS  = {"Authorization": f"Bearer {TOKEN}",
            "Accept":        "application/json"}

# ---------------------------------------------------------------------------
# 1.  Generic helper – handles offset/limit pagination for any GET endpoint
# ---------------------------------------------------------------------------
def paged_get(endpoint: str,
              params: Dict[str, Any] | None = None,
              page_size: int = 100) -> Generator[Dict[str, Any], None, None]:
    """
    Stream JSON objects from a paginated Tempo endpoint.

    >>> for obj in paged_get("/accounts"):
    ...     print(obj)
    """
    offset = 0
    params = params or {}
    while True:
        params.update({"offset": offset, "limit": page_size})
        resp = requests.get(BASE_URL + endpoint, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        yield from payload.get("results", [])
        if offset + page_size >= payload.get("metadata", {}).get("count", 0):
            break
        offset += page_size
        time.sleep(0.2)   # be nice to the API rate limits

# ---------------------------------------------------------------------------
# 2.  Example A – list all Tempo Accounts you have access to
# ---------------------------------------------------------------------------
def dump_accounts() -> List[Dict[str, Any]]:
    accounts = list(paged_get("/accounts"))
    print(f"✔  Pulled {len(accounts)} accounts")
    return accounts

# ---------------------------------------------------------------------------
# 3.  Example B – fetch worklogs for a project & date window
# ---------------------------------------------------------------------------
def dump_worklogs(jira_project_key: str,
                  days_back: int = 7) -> List[Dict[str, Any]]:
    end   = date.today()
    start = end - timedelta(days=days_back)
    params = {"from": start.isoformat(),
              "to":   end.isoformat(),
              "project": jira_project_key}
    worklogs = list(paged_get("/worklogs", params=params))
    print(f"✔  Pulled {len(worklogs)} worklogs for {jira_project_key} "
          f"{start} → {end}")
    return worklogs

# ---------------------------------------------------------------------------
# 4.  Entry-point – run the samples
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    dump_accounts()                    # demo 1
    dump_worklogs("FIN")               # demo 2 – replace FIN with your Jira key
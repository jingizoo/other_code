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

### Why the call is still failing

| Error you see                                                   | What it actually means                                                                                                                                                                                                      | How to solve                                                                                        |
| --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **`400 Bad Request …project=FIN`**                              | Tempo REST API v4 no longer accepts a *project key* in the `project` query-parameter – it must be the numeric **project ID**. The server throws 400 as soon as it sees an alphanumeric value. ([tempo-io.atlassian.net][1]) | Pass the ID (e.g. `project=10023`) *or* drop the parameter altogether.                              |
| **`certificate verify failed … self-signed…`** (only a warning) | Your company proxy is doing SSL interception and re-signing Tempo’s TLS certificate with an internal CA that Python doesn’t trust.                                                                                          | Either supply the corporate CA bundle (recommended) or keep `verify=False` and silence the warning. |

---

## 1 – Find your Jira project’s numeric ID (one-off)

**Quickest:** paste this into any browser while logged into Jira:

```
https://<your-site>.atlassian.net/rest/api/3/project/FIN
```

Look for `"id": "10023"` (the string inside quotes is the ID you need).

*No admin rights required; only browse permission for the project.*

---

## 2 – Patch your script (two-line change)

```python
# ---------------------------------------------
PROJECT_ID = "10023"          # ← paste the number you just found
# ...
params = {
    "from": start.isoformat(),
    "to":   end.isoformat(),
    "project": PROJECT_ID      # must be the ID, not the key
}
# ---------------------------------------------
logs = list(paged_get("/worklogs", params=params))
```

Run it again – the 400 disappears and the work-logs stream in.

---

## 3 – (Optionally) automate the key ➜ ID lookup

If you don’t want to hard-code the ID, pull it dynamically once per run:

```python
def key_to_id(key: str) -> str:
    url = f"https://{os.getenv('JIRA_SITE')}/rest/api/3/project/{key}"
    r = requests.get(url,
                     headers={"Authorization": f"Basic {os.getenv('JIRA_TOKEN')}",
                              "Accept": "application/json"},
                     timeout=30,
                     verify=VERIFY_SSL)
    r.raise_for_status()
    return r.json()["id"]
```

Then use `project = key_to_id("FIN")`.

---

## 4 – Get rid of the SSL warnings (safe way)

1. Export your organisation’s root CA certificate to a file, e.g. `corp_root.pem`.
2. Tell Requests to use it:

```bash
# Windows PowerShell
setx REQUESTS_CA_BUNDLE "C:\certs\corp_root.pem"

# macOS / Linux
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/corp_root.pem
```

Now remove the temporary `verify=False` from your code; the proxy’s certificate will validate cleanly and the warnings vanish.

---

### TL;DR

* Replace `project=FIN` with `project=<numeric-ID>` → no more **400**.
* Point Requests at your corporate CA bundle or keep `verify=False` if you must.
* Everything else in the earlier sample stays the same – your token, paging logic, etc.

[1]: https://tempo-io.atlassian.net/wiki/spaces/HCTIMESHEETS/pages/3374321623/Tempo%2BAPI%2Bversion%2B4.0%2Bvs.%2Bversion%2B3.0%2BA%2Bcomparison "Tempo API version 4.0 vs. version 3.0: A comparison - Help Center - Timesheets (Cloud) - Tempo Confluence"

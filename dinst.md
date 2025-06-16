Below is a **from-scratch checklist** you can follow once and forget.
Start in the **repo root** that already contains

```
src/main/python/psdata/…
└─ delete_tables.py          # ← the script you want to dockerise
```

> **Goal**: after these steps every merge builds two container tags
> `…/lifecycle-retention:soft` and `…:nonstop` and Batch can schedule them.

---

## 1  Prepare the script (1 min)

```python
# src/main/python/psdata/delete_tables.py
import argparse, logging, sys

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["soft", "hard"], default="soft")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    logging.info("Running in %s mode", args.mode)

    if args.mode == "soft":
        soft_delete()        # TODO: flag/move data
    else:
        hard_delete()        # TODO: irreversible delete

if __name__ == "__main__":
    main()
```

---

## 2  Add **dependencies**

Create **`requirements.txt`** (even if it’s empty for now):

```
typer==0.12.3        # add real libs here
```

---

## 3  Bootstrap Gradle wrapper (30 s)

```bash
cd <repo-root>
gradle wrapper --gradle-version 8.6
git add gradlew gradlew.bat gradle/wrapper
```

*(If the wrapper already exists, skip.)*

---

## 4  Create **`settings.gradle`**

```groovy
rootProject.name = 'psdata-lifecycle-retention'
```

---

## 5  Create **`build.gradle`**

```groovy
plugins {
    id 'com.citadel.python-project' version '1.5.0'
    id 'com.citadel.cigdocker'      version '1.5.0'
}

python {
    srcDir = file('src/main/python')        // plugin needs to know where code is
}

cigdocker {
    createDockerImage = true

    imageName = 'psdata/lifecycle-retention'
    baseImage = 'artifactory.citadelgroup.com/docker-remote/python:3.12-slim'

    extraTags = ['soft', 'nonstop']         // build both tags from one image

    includeServiceRouterSidecarRunner = false   // you don’t need the sidecar

    // optional system packages for gsutil / gcc etc.
    dockerPrependFile = file('Dockerfile.pre')
}
```

---

## 6  (Optional) **`Dockerfile.pre`** – OS libs you might need

```dockerfile
# Dockerfile.pre
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc build-essential && \
    rm -rf /var/lib/apt/lists/*
```

Skip if you don’t need extra packages.

---

## 7  Ignore build artefacts

Add to **`.gitignore`**

```
build/
```

---

## 8  Local sanity test (optional but recommended)

```bash
# generate Dockerfile & helper script
./gradlew dockerfile

# build locally
./build/Dockerfile.python.sh

# run container once
docker run --rm psdata/lifecycle-retention:local-$(date +%s) --mode soft --dry-run
```

If it prints *“Running in soft mode”* you’re good.

---

## 9  Commit & push

```bash
git add build.gradle settings.gradle Dockerfile.pre requirements.txt .gitignore
git commit -m "Enable cigdocker auto-build with soft & nonstop tags"
git push origin main
```

---

## 10  What happens in CitSource CI (CDX)

1. Detects `createDockerImage = true`.
2. Generates Dockerfile, inserts `Dockerfile.pre`.
3. Builds image once → retags: `:soft`, `:nonstop`.
4. Pushes to **Artifactory** `docker-dev-01-local/psdata/lifecycle-retention:*`
5. Pushes/signed to **Google Artifact Registry**.
6. Labels image with

   ```
   citsource-git-commit=<commit SHA>
   citsource-build-id   =<build number>
   ```

You’ll see these steps in the pipeline log.

---

## 11  Register tags in **Batch UI → Docker**

| Key                 | Image location (copy exact FQDN)                                                      |
| ------------------- | ------------------------------------------------------------------------------------- |
| `lifecycle-soft`    | `artifactory.citadelgroup.com/docker-dev-01-local/psdata/lifecycle-retention:soft`    |
| `lifecycle-nonstop` | `artifactory.citadelgroup.com/docker-dev-01-local/psdata/lifecycle-retention:nonstop` |

*(Use `docker-qa-01-local` or `docker-prod-01-local` if that’s your policy.)*

---

## 12  Create two Batch / Accounting-Gateway jobs

```yaml
# --- soft delete job ---------------------------------
image: artifactory.citadelgroup.com/docker-dev-01-local/psdata/lifecycle-retention:soft
command: []                      # ENTRYPOINT already defaults to --mode soft
schedule: "0 3 * * SUN"          # example weekly run

# --- non-stop (hard) delete job ----------------------
image: artifactory.citadelgroup.com/docker-dev-01-local/psdata/lifecycle-retention:nonstop
command: []                      # defaults to --mode hard
schedule: "0 4 1 * *"            # example monthly run
```

Save → enable schedule → done.

---

### You’re finished ✔︎

* **Dev flow**: `./gradlew dockerfile` + `./build/Dockerfile.python.sh` to test.
* **CI flow**: CDX auto-builds & auto-pushes tags each merge.
* **Ops flow**: Scheduler just selects `:soft` or `:nonstop` and runs.
# psdata/soft_archive.py
```
from google.cloud import bigquery
import logging
import datetime as dt

def snapshot_then_delete(
    client: bigquery.Client,
    project: str,
    dataset: str,
    table: str,
    year: int,
    dry_run: bool = False,
):
    ts = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    src  = f"`{project}.{dataset}.{table}`"
    snap = f"`{project}.{dataset}.__snap_{table}_{ts}`"

    # 1) make snapshot (zero-copy clone valid for 7 days unless you keep it longer)
    snap_sql = f"CREATE SNAPSHOT TABLE {snap} CLONE {src} OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 30 DAY))"
    # 2) run delete
    del_sql  = f"DELETE FROM {src} WHERE fy_partition = @year"

    if dry_run:
        logging.info("[DRY-RUN] would run:\n%s;\n%s;\n", snap_sql, del_sql)
        return

    logging.info("↪︎ snapshotting rows to %s", snap)
    client.query(snap_sql).result()

    logging.info("✂︎ deleting fiscal-year %s from %s", year, src)
    job = client.query(
        del_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("year", "INT64", year)]
        ),
    )
    job.result()
    logging.info("✓ %d row(s) deleted; snapshot keeps full copy", job.num_dml_affected_rows)
```

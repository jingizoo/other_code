## 1️⃣ Overview

First cut of the PeopleSoft → GCS → BigQuery pipeline codebase.
Adds a working end-to-end flow and basic project structure.

---

### What’s included

* **Package skeleton** under `psdata/` (`etl`, `parquet`, `gcs`, `bq`, `sqlserver`).
* **Row-chunk extractor** (`etl/extract_sql.py`) → writes `PS_TABLE-part000.parquet` etc.
* **Uploader** (`etl/upload_gcs.py`) → pushes chunks to GCS and cleans old files.
* **Terraform generator** (`etl/gen_terraform.py`) → builds `bq_tables.tf` and load jobs.
* Minimal **config loader**, GCS & BigQuery helper stubs.
* README scaffold.

### Why start here?

Gives the team a runnable baseline so we can iterate in small PRs:

* try real extracts,
* plug in unit tests,
* refine schema handling,
* add CI later.

---

## ✅ Smoke test performed

* Ran `extract_sql` against **dev** DB – 2 small tables extracted.
* `upload_gcs` pushed to dev bucket (`finsup/`).
* `terraform apply` loaded both tables into `ps_archive` dataset.

All steps completed without errors.

---

## 🙏 Review focus

* Directory layout & module names ok?
* Any deal-breaker coding-style issues before we build on this?

---

*(merge when green – downstream branches will extend on this foundation)*

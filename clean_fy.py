#!/usr/bin/env python3
"""
clean_fy.py — One‑stop fiscal‑year cleanup for **BigQuery** rows *and* **GCS** objects.

Features
~~~~~~~~~
• Lists every BigQuery table that contains a column named `fy_partition`
  and deletes the rows where `fy_partition = <year>`.
• Deletes (or previews) all objects in Cloud Storage that live under
  the path pattern
      gs://<bucket>/<root>/<module>/FY<year>/...
  where <module> defaults to “*” = any top‑level module (AM, GL, static…).
• Interactive **--dry‑run** preview and yes/no confirmation.
• Independent toggles — run *only* table deletes or *only* file deletes.

Requirements
~~~~~~~~~~~~
‣ Python 3.8+  ‣ google‑cloud‑bigquery  ‣ google‑cloud‑storage  
  (Install:  `pip install google-cloud-bigquery google-cloud-storage`)
‣ gcloud auth **must** be set so the script can use ADC credentials.

Usage examples
~~~~~~~~~~~~~~
# Preview everything that would be deleted for FY2015.
python clean_fy.py --project cig-accounting-dev-1 --dataset ps_archive \
                   --bucket peoplesoft-cold-storage-archieve \
                   --root finsup --year 2015 --dry-run

# Real delete, tables *and* files, but only inside module AM
python clean_fy.py --project cig-accounting-dev-1 --dataset ps_archive \
                   --bucket peoplesoft-cold-storage-archieve \
                   --root finsup --module AM --year 2015

# Only clean the files (keep BQ rows)
python clean_fy.py --files-only ... (rest of args) ...

# Only clean the tables
python clean_fy.py --tables-only ... (rest of args) ...
"""
import argparse
import sys
from pathlib import PurePosixPath
from google.cloud import bigquery, storage

# ───────────────────────── Helper prompts ──────────────────────────

def prompt_yes_no(message: str) -> bool:
    """Simple Y/N prompt; returns True for yes."""
    while True:
        ans = input(f"{message} [y/n]: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please type y or n.")

# ─────────────────────── BigQuery helpers ─────────────────────────

def list_tables_with_fy(client: bigquery.Client, project: str, dataset: str):
    sql = f"""
        SELECT DISTINCT table_name
        FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
        WHERE LOWER(column_name) = 'fy_partition'
    """
    return [row.table_name for row in client.query(sql).result()]

def delete_year_from_table(client: bigquery.Client, project: str, dataset: str,
                           table: str, year: int, dry_run: bool):
    fq_table = f"`{project}.{dataset}.{table}`"
    sql = f"DELETE FROM {fq_table} WHERE fy_partition = {year}"
    if dry_run:
        print("DRY‑RUN:", sql)
        return
    job = client.query(sql)
    job.result()
    print(f"✓ {table}: {job.num_dml_affected_rows} row(s)")

# ───────────────────── Google Cloud Storage helpers ───────────────

def build_prefix(root: str, module: str, year: int) -> str:
    # Construct finsup/**/FY2015/** pattern
    if module == "*":
        # Wildcard module means list from root and filter later
        return f"{root}/"
    return f"{root}/{module}/FY{year}/"

def delete_objects(storage_client: storage.Client, bucket_name: str,
                   prefix: str, year: int, module: str, dry_run: bool):
    bucket = storage_client.bucket(bucket_name)

    # If module == '*', list all and filter by /FYyyyy/
    if module == "*":
        blobs = [b for b in bucket.list_blobs(prefix=prefix)
                 if f"/FY{year}/" in b.name]
    else:
        blobs = list(bucket.list_blobs(prefix=prefix))

    if not blobs:
        print("No objects matched the pattern — nothing to delete.")
        return

    print(f"Found {len(blobs)} object(s) to delete in gs://{bucket_name}/{prefix}…")
    if dry_run:
        for b in blobs[:10]:
            print("DRY‑RUN:", b.name)
        if len(blobs) > 10:
            print("… (total", len(blobs), "objects)")
        return

    for blob in blobs:
        blob.delete()
    print("✓ Deleted", len(blobs), "object(s)")

# ───────────────────────────── Main ───────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Delete one fiscal‑year slice from BigQuery + GCS.")
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--dataset", required=True, help="BigQuery dataset ID")
    parser.add_argument("--bucket", required=True, help="GCS bucket name")
    parser.add_argument("--root", default="finsup", help="Top‑level folder inside bucket")
    parser.add_argument("--module", default="*", help="Module folder (AM|GL|static|*)")
    parser.add_argument("--year", type=int, required=True, help="Fiscal year, e.g. 2015")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--files-only", action="store_true", help="Delete only GCS files")
    group.add_argument("--tables-only", action="store_true", help="Delete only BigQuery rows")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    # Summary prompt
    scope = "files only" if args.files_only else "tables only" if args.tables_only else "files + tables"
    print("\nCleanup plan: fiscal year", args.year, "→", scope)
    print("Project:", args.project, " | Dataset:", args.dataset)
    print("Bucket:", args.bucket, " | Root:", args.root, " | Module:", args.module)
    if args.dry_run:
        print("*** DRY‑RUN mode: no data will be deleted ***")

    if not prompt_yes_no("Proceed?"):
        sys.exit("Aborted by user.")

    # ─── Files section ────────────────────────────────────────────
    if not args.tables_only:
        storage_client = storage.Client(project=args.project)
        prefix = build_prefix(args.root, args.module, args.year)
        delete_objects(storage_client, args.bucket, prefix, args.year,
                       args.module, args.dry_run)

    # ─── Tables section ───────────────────────────────────────────
    if not args.files_only:
        bq_client = bigquery.Client(project=args.project)
        tables = list_tables_with_fy(bq_client, args.project, args.dataset)
        print(f"\n{len(tables)} table(s) include fy_partition.")
        for tbl in tables:
            delete_year_from_table(bq_client, args.project, args.dataset,
                                   tbl, args.year, args.dry_run)

if __name__ == "__main__":
    main()

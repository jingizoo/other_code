Deleting a Fiscal-Year Partition (FY2015) – User Guide

Scope  Remove one fiscal-year slice (e.g. 2015) from both
GCS parquet folders and BigQuery native tables only if the table contains the column fy_partition.

• Tables without that column are left untouched.
• You can run an automated PowerShell script or follow the manual console steps.

⸻

Data layout recap

Layer	Partition logic	Example target for FY2015
GCS	Folder path contains the year	gs://peoplesoft-cold-storage-archieve/finsup/GL/FY2015/PS_VCHR_ACCTG_LINE.parquet
BigQuery	Column fy_partition (INT) = 2015	DELETE … WHERE fy_partition = 2015


⸻

1  Automated removal (PowerShell)

Save as Delete-FY.ps1

param(
  [Parameter(Mandatory=$true)][int] $Year,
  [string] $Module = "*"   # top-level folder (AM | GL | static | *)
)

$Bucket   = "peoplesoft-cold-storage-archieve"
$Prefix   = "finsup"
$Dataset  = "ps_archive"
$Project  = "cig-accounting-dev-1"

# 1️⃣ wipe parquet under the FY folder
$gcsPath = if ($Module -eq '*') {
    "$Prefix/**/FY$Year/**"
} else {
    "$Prefix/$Module/FY$Year/**"
}
gsutil -m rm -r "gs://$Bucket/$gcsPath"

# 2️⃣ find only tables that *have* fy_partition
$tblQuery = @"
SELECT table_name
FROM   `$Project.$Dataset.INFORMATION_SCHEMA.COLUMNS`
WHERE  column_name = 'fy_partition'
"@
$bqTables = bq query --use_legacy_sql=false --nouse_cache --format=csv $tblQuery |
            Select-Object -Skip 1  # drop header

foreach ($tbl in $bqTables) {
    Write-Host "Deleting FY$Year from $tbl…"
    bq query --use_legacy_sql=false --project_id=$Project \
      "DELETE FROM `$Project.$Dataset.$tbl` WHERE fy_partition = $Year;"
}

Write-Host "✓ FY$Year removed from all tables that include fy_partition."

Run:

./Delete-FY.ps1 -Year 2015 -Module "GL"

(omit -Module to delete across all modules)

⸻

2  Manual steps

2.1  Delete parquet files
	1.	Cloud Storage › Browser → navigate to bucket/prefix.
	2.	Use the filter box: FY2015 → tick the checkbox at top → Delete.

2.2  Delete BQ rows (only tables with fy_partition)

-- list target tables
SELECT table_name
FROM   `cig-accounting-dev-1.ps_archive.INFORMATION_SCHEMA.COLUMNS`
WHERE  column_name = 'fy_partition';

For each table returned:

DELETE FROM `cig-accounting-dev-1.ps_archive.<TABLE>`
WHERE  fy_partition = 2015;


⸻

3  Rollback

Restore the FY folder from backup and rerun the ETL → Terraform apply.  Tables reload fy_partition = 2015 automatically.

⸻

4  FAQ (updated)

Q	A
Table lacks fy_partition but still has FY in filename?	The BigQuery step skips it; you may still remove the parquet if desired.
Do I need to rewrite schema?	No; deleting rows does not touch schema.

Maintainer  – Data Engineering Team
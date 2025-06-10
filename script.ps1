<#
Delete-FyPartition-Json.ps1
--------------------------
Remove one fy_partition slice from all tables in a BigQuery dataset,
using JSON output from `bq query`.

Usage
  pwsh .\Delete-FyPartition-Json.ps1 `
       -Project  cig-accounting-dev-1 `
       -Dataset  peoplesoft_archive  `
       -Year     2015 `
       -Location asia-south1         # optional
  # Dry-run
  … -WhatIf
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Project,
    [Parameter(Mandatory)][string]$Dataset,
    [Parameter(Mandatory)][int]   $Year,
    [string]$Location,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

# ──────────────────────────────────────────────────────────────────────────
function Invoke-BqJson {
<#
Runs a BigQuery SQL string and returns a PowerShell object array
parsed from the JSON array produced by `bq --format=prettyjson`.

Silently drops any non-JSON lines (job chatter, Python banner, blanks).
#>
    param([string]$Sql)

    $baseArgs = @('--nouse_legacy_sql', '--quiet', '--format=prettyjson')
    if ($Location) { $baseArgs += @('--location', $Location) }
    $baseArgs += $Sql

    $raw = (& bq query @baseArgs 2>&1)                           # capture all output
    if (-not $raw) { throw 'bq returned no output.' }

    # Keep only lines that look like JSON (start with "[" or "{")
    $jsonLines = $raw | Where-Object { $_.Trim() -match '^[\[{]' }

    if (-not $jsonLines) {
        throw "No JSON payload detected in bq output. Raw output:`n$($raw -join "`n")"
    }

    # Join the JSON lines back into a single string and parse
    $jsonText = $jsonLines -join "`n"
    return $jsonText | ConvertFrom-Json
}

# ──────────────────────────────────────────────────────────────────────────
Write-Host "`n► Gathering tables that contain 'fy_partition' in $Project.$Dataset …" `
           -Foreground Cyan

$tblQuery = @"
SELECT DISTINCT table_name
FROM   `$Project.$Dataset.INFORMATION_SCHEMA.COLUMNS`
WHERE  LOWER(column_name) = 'fy_partition'
"@

$tableObjs  = Invoke-BqJson $tblQuery
$tableNames = $tableObjs | Select-Object -ExpandProperty table_name

if (-not $tableNames) {
    Write-Warning 'No tables contain fy_partition — nothing to delete.'
    return
}

Write-Host "✔  Found $($tableNames.Count) table(s)." -Foreground Green

# ──────────────────────────────────────────────────────────────────────────
foreach ($tbl in $tableNames) {
    $fullId = "``$Project.$Dataset.$tbl``"      # escape back-ticks for BigQuery
    $delSql = "DELETE FROM $fullId WHERE fy_partition = $Year;"

    if ($WhatIf) {
        Write-Host "[WHATIF] $delSql"
        continue
    }

    Write-Host ("→ Deleting FY{0} rows from {1} …" -f $Year, $tbl) -Foreground Yellow
    try {
        Invoke-BqJson $delSql | Out-Null        # run DELETE, ignore JSON reply
        Write-Host "   ✓ Done" -Foreground Green
    }
    catch {
        Write-Warning "   ⚠ Failed on $tbl : $_"
    }
}

if (-not $WhatIf) { Write-Host "`nAll deletions complete." -Foreground Green }

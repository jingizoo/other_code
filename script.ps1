Below is a **ready-to-run PowerShell 7 script** that

1. finds every table in a BigQuery dataset that contains a column named `fy_partition`, and
2. deletes the rows whose `fy_partition = <Year>`.

Save it as **`Delete-FyPartition.ps1`**, tweak the parameters, and run.

```powershell
<#
.SYNOPSIS
    Delete one fiscal-year slice (fy_partition) from all tables in a BigQuery dataset.

.DESCRIPTION
    • Lists tables whose schema includes a column called fy_partition  
    • Executes DELETE … WHERE fy_partition = <Year> on each table

    Prerequisites
      – gcloud SDK / bq CLI installed and authenticated
      – Account has BigQuery Data Editor on the dataset / tables
      – PowerShell 7 (pwsh) or later

.EXAMPLE
    ./Delete-FyPartition.ps1 -Project cig-accounting-dev-1 `
        -Dataset peoplesoft_archive -Year 2015 -Location asia-south1

    # dry-run (prints SQL only)
    ./Delete-FyPartition.ps1 -Project myproj -Dataset myds -Year 2020 -WhatIf
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Project,

    [Parameter(Mandatory)]
    [string]$Dataset,

    [Parameter(Mandatory)]
    [int]$Year,

    # Optional BigQuery location/region (us, europe-west2, asia-south1, …)
    [string]$Location = $null,

    # Switch: show the DELETE statements without executing them
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

function Invoke-BqJson {
    param([string]$Sql)

    $args = @('--nouse_legacy_sql', '--quiet', '--format=prettyjson')
    if ($Location) { $args += @('--location', $Location) }
    $args += $Sql

    & bq query @args
}

try {
    Write-Host "► Gathering tables that contain 'fy_partition' in $Project.$Dataset …" -Foreground Cyan

    # -------- 1. Get table list -------------------------------------------------
    $tblQuery = @"
SELECT DISTINCT table_name
FROM   ``$Project.$Dataset.INFORMATION_SCHEMA.COLUMNS``
WHERE  LOWER(column_name) = 'fy_partition'
"@

    $tableObjs  = Invoke-BqJson $tblQuery | ConvertFrom-Json
    $tableNames = $tableObjs | Select-Object -ExpandProperty table_name

    if (-not $tableNames) {
        Write-Warning "No tables contain fy_partition — nothing to delete."
        return
    }

    Write-Host ("✔ Found {0} table(s)." -f $tableNames.Count) -Foreground Green

    # -------- 2. Delete rows ----------------------------------------------------
    foreach ($tbl in $tableNames) {
        $fullId = ("``{0}.{1}.{2}``" -f $Project, $Dataset, $tbl)   # back-ticks escaped
        $delSql = "DELETE FROM $fullId WHERE fy_partition = $Year;"

        if ($WhatIf) {
            Write-Host "[WHATIF] $delSql"
            continue
        }

        Write-Host ("→ Deleting FY{0} rows from {1} …" -f $Year, $tbl) -Foreground Yellow
        try {
            Invoke-BqJson $delSql | Out-Null
            Write-Host "   ✓ Done" -Foreground Green
        }
        catch {
            Write-Warning "   ⚠ Failed on $tbl : $_"
        }
    }

    if (-not $WhatIf) { Write-Host "All deletions complete." -Foreground Green }
}
catch {
    Write-Error $_
}
```

**How to use**

```powershell
# real delete
pwsh ./Delete-FyPartition.ps1 `
     -Project cig-accounting-dev-1 `
     -Dataset peoplesoft_archive `
     -Year    2015 `
     -Location asia-south1

# dry-run first
pwsh ./Delete-FyPartition.ps1 -Project myproj -Dataset myds -Year 2020 -WhatIf
```

Key points handled:

| Issue                               | How the script deals with it                         |
| ----------------------------------- | ---------------------------------------------------- |
| CSV header `table_name` sneaking in | Uses `--format=prettyjson` → header-less JSON        |
| CLI noise (“Waiting on job…”)       | `--quiet` flag                                       |
| Back-ticks disappearing             | Every literal back-tick is doubled (\`\`) in strings |
| Empty result set                    | Early exit with a clear warning                      |
| Safe preview                        | `-WhatIf` switch prints SQL but skips execution      |

Drop this into your repo, parameterise it in a CI job if you like, and you have a repeatable fiscal-year cleanup utility. Let me know if you hit any corner cases!

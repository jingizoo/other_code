<#
Delete-FyFiles.ps1
──────────────────
Wipe Parquet (or any) files for a specific FY partition in GCS.

USAGE EXAMPLES
  # dry-run: list what would be removed
  pwsh .\Delete-FyFiles.ps1 -Year 2015 -WhatIf

  # delete FY2015 for all modules
  pwsh .\Delete-FyFiles.ps1 -Year 2015

  # delete FY2015 only under the AM module
  pwsh .\Delete-FyFiles.ps1 -Year 2015 -Module AM
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true)]
    [int]$Year,

    # AM | GL | static | *  (default = * for “all modules”)
    [string]$Module = "*",

    [switch]$WhatIf
)

# ─── bucket layout — adjust here if it ever changes ─────────────────────────
$Bucket  = "peoplesoft-cold-storage-archieve"
$Prefix  = "finsup"                     # top-level folder just under the bucket
# ---------------------------------------------------------------------------

# Build the gsutil “glob” we want to delete
$gcsPath = if ($Module -eq "*") {
    "$Prefix/**/FY$Year/**"
} else {
    "$Prefix/$Module/FY$Year/**"
}
$Uri = "gs://$Bucket/$gcsPath"

Write-Host "`n► Scanning  $Uri" -Foreground Cyan

# 1 ─ find objects
$objects = & gsutil ls -r $Uri 2>$null
$cnt     = $objects.Count

if ($cnt -eq 0) {
    Write-Warning "No objects found — nothing to delete."
    return
}
Write-Host "✔  Found $cnt object(s)." -Foreground Green

# 2 ─ preview mode?
if ($WhatIf) {
    Write-Host "[WHATIF] Would run:  gsutil -m rm -r $Uri"
    return
}

# 3 ─ safety confirmation (Ctrl-C aborts)
if (-not $PSCmdlet.ShouldProcess($Uri, "Delete $cnt object(s)")) { return }

# 4 ─ delete
Write-Host "`n→ Deleting …" -Foreground Yellow
& gsutil -m rm -r $Uri 2>$null
Write-Host "`n✓ Completed." -Foreground Green

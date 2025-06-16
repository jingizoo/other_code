#!/usr/bin/env python3
"""
archive_report.py ─ Summarise the output of related_extract_v2.py

For every module configured in psdata.yaml it discovers:
    • All tables whose primary-key starts with the module’s key table keys
    • Every Parquet file written by the extractor (FY-folders, FY2099, static)
    • The rule (“FY window” or “Orphan”) that decided the destination

It then prints / saves a tabular report:

| module | table            | parent_table | partition | criteria                                |
|--------|------------------|--------------|-----------|-----------------------------------------|
| GL     | PS_JRNL_HEADER   | PS_JRNL_HDR  | FY2024    | ACCOUNTING_DT between 2023-07-01/24-06-30 |
| GL     | PS_JRNL_HEADER   | PS_JRNL_HDR  | FY2099    | orphan rows (no hit in date_table)      |
| …      | …                | …            | static    | static table (no FY slicing)            |
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Iterable, Dict

import pandas as pd
import typer
import pyodbc

# ---- import the same helpers your ETL already ships --------------------
from psdata.config.loader import load_config
from related_extract_v2 import (
    get_key_columns,
    tables_with_keys,
    table_exists,
)  # re-use proven logic

app = typer.Typer(add_help_option=True, no_args_is_help=True)


def _scan_parquet_folders(staging_root: Path) -> Dict[str, List[str]]:
    """
    Return {partition: [table1, table2, …]} by naming convention:
        FY2024/PS_JRNL_HEADER.parquet   -> partition = FY2024
        static/PS_LEDGER.parquet        -> partition = static
        FY2099/PS_JRNL_HEADER_FY2099.parquet -> partition = FY2099
    """
    out: Dict[str, List[str]] = {}
    for part_dir in staging_root.glob("*"):
        if not part_dir.is_dir():
            continue
        partition = part_dir.name.upper()       # FY2024, FY2099, STATIC …
        for pq in part_dir.glob("*.parquet"):
            tbl = pq.stem.split("_FY")[0].upper()   # strip _FY2099 suffix
            out.setdefault(partition, []).append(tbl)
    return out


def _iter_rows(env: str) -> Iterable[dict]:
    cfg = load_config(env)
    staging_root = Path(cfg.local.staging_dir)

    # map partition->tables actually present on disk
    present = _scan_parquet_folders(staging_root)

    with pyodbc.connect(cfg.sql.dsn, autocommit=True) as conn:
        for mod, mcfg in (cfg.modules if hasattr(cfg, "modules") else cfg["modules"]).items():
            mod = mod.upper()
            keys = get_key_columns(conn, mcfg.key_table)
            rel_tables = [
                t for t in tables_with_keys(conn, keys)
                if table_exists(conn, t) and any(t in tbls for tbls in present.values())
            ]

            for tbl in rel_tables:
                for tbl in rel_tables:
    # ── one row for every FY that WILL be extracted ──
                    for fy in range(first_fy, last_fy + 1):
                        start = pd.Timestamp(year=fy - 1, month=cfg.fy_start_month, day=1)
                        end   = pd.Timestamp(year=fy, month=cfg.fy_start_month, day=1) - pd.Timedelta(days=1)
                        yield {
                            "module": mod,
                            "table": tbl,
                            "parent_table": mcfg.key_table.upper(),
                            "partition": f"FY{fy}",
                            "criteria": f"{mcfg.date_col} between {start:%Y-%m-%d}/{end:%Y-%m-%d}",
                        }
                
                    # ── one virtual bucket for orphans ──
                    yield {
                        "module": mod,
                        "table": tbl,
                        "parent_table": mcfg.key_table.upper(),
                        "partition": "FY2099",
                        "criteria": "orphan rows (no match in date_table)",
                    }



@app.command()
def report(
    env: str = typer.Argument(..., help="Config environment (dev | prod | …)"),
    out_csv: Path = typer.Option(
        None, "--csv", "-o", help="Write report to CSV instead of stdout"
    ),
) -> None:
    """
    Produce the archive summary.  By default prints an aligned Markdown-friendly
    table to stdout; with --csv writes a machine-readable file.
    """
    rows = list(_iter_rows(env))
    df = pd.DataFrame(rows).sort_values(["module", "table", "partition"])

    if out_csv:
        df.to_csv(out_csv, index=False, quoting=csv.QUOTE_NONNUMERIC)
        typer.secho(f"✓ Report written → {out_csv}", fg=typer.colors.GREEN)
    else:
        # pretty console output (Markdown-style)
        str_tbl = df.to_markdown(index=False)
        typer.echo(str_tbl)


if __name__ == "__main__":
    app()

Retention     : 7 fiscal years
Today         : FY2025
Delete window : FY2017 and older  (unless on hold)

┌──────────────────────────────────────┐
│ gs://ps-archive/module/              │
│   FY2015/      ← delete candidate ✔  │
│   FY2016/      ← delete candidate ✔  │
│   FY2017/      ← delete candidate ✔  │
│   FY2018/      ← KEEP (within window)│
│   …                                   │
│   FY2099/      ← orphan quarantine   │
└──────────────────────────────────────┘

flowchart TD
    %% ────────── 1) Setup ──────────
    A[Module definition<br/>(key_table, date_table, date_col)] --> B[Driving table<br/>(date_table)]

    %% ────────── 2) Determine canonical date ──────────
    B --> C{ACCOUNTING_DT<br/>present & valid?}

    C -- "Yes" --> D[Canonical date =<br/>MIN(ACCOUNTING_DT)<br/>per business key]
    D --> E[Compute FY =<br/>_fiscal_year(canonical_date)]

    %% ────────── 3) Tag & write ──────────
    E --> F[Stamp FY on all<br/>related tables]
    F --> G[Write rows →<br/>gs://archive/&lt;module&gt;/FY####/]

    %% ────────── 4) Orphans ──────────
    C -- "No / out-of-range" --> H[Route rows →<br/>FY2099<br/>(orphan quarantine)]

    %% ────────── 5) Static tables ──────────
    S[Reference / lookup tables] --> T[Write once →<br/>static/]


“For each module we point to its authoritative ‘date table’—the one Finance already uses to close the books.
We take the earliest accounting date for each business object, convert it to the fiscal year, and stamp that same year on every related row across all detail tables.
Those rows stream straight into a folder named after the fiscal year (FY2023, FY2024, etc.).

If a row is missing its accounting date or the date makes no sense, we park it in FY2099 so it can’t corrupt the real partitions.

The result is that every record sits in exactly one fiscal-year folder, making retention and audit queries very straightforward.”

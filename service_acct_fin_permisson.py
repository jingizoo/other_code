#!/usr/bin/env python3
"""
list_sa_roles.py
────────────────
Use a *service-account* key file (JSON) to:
  • authenticate all API calls
  • read the service-account email from the file
  • search every IAM policy under the chosen scope
  • print every distinct role the account holds

Usage
-----
    python list_sa_roles.py \
        /path/to/key.json \
        my-project-id          # or 123456789012 (folder / org ID)

Requirements
------------
    pip install google-cloud-asset google-auth
"""

from __future__ import annotations
import argparse
from typing import Set

from google.oauth2 import service_account           # pip install google-auth
from google.cloud import asset_v1                   # pip install google-cloud-asset


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────
def normalize_scope(raw: str) -> str:
    """Attach Resource-Manager prefix if caller omitted it."""
    if raw.startswith(("projects/", "folders/", "organizations/")):
        return raw
    if raw.isdigit() and len(raw) == 12:
        return f"folders/{raw}"        # 12-digit → assume folder / org
    return f"projects/{raw}"           # default to project


def find_roles(asset_client: asset_v1.AssetServiceClient,
               principal: str,
               scope: str) -> Set[str]:
    """Return every role string in which *principal* appears under *scope*."""
    query = f'policy:"{principal}"'
    pager = asset_client.search_all_iam_policies(
        request={"scope": scope, "query": query}
    )
    roles: Set[str] = set()
    for result in pager:
        for b in result.policy.bindings:
            if principal in b.members:
                roles.add(b.role)
    return roles


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="List every IAM role a service-account holds in the scope."
    )
    parser.add_argument("keyfile",  help="Path to service-account key JSON")
    parser.add_argument("scope_id", help="Project-ID | Folder-ID | Org-ID")
    args = parser.parse_args()

    # 1️⃣  Build credentials & get the SA email from the key file
    creds = service_account.Credentials.from_service_account_file(
        args.keyfile,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    sa_email = creds.service_account_email
    principal = f"serviceAccount:{sa_email}"

    scope = normalize_scope(args.scope_id)

    # 2️⃣  Create Cloud Asset client with those creds
    asset_client = asset_v1.AssetServiceClient(credentials=creds)

    print(f"\n🔎  Searching IAM under {scope!r} for {principal!r} …")

    # 3️⃣  Collect roles
    roles = find_roles(asset_client, principal, scope)
    if not roles:
        print("🙅  No roles found.")
        return

    print(f"\n🗂️   {len(roles)} roles found for {sa_email}:\n")
    for r in sorted(roles):
        print(" •", r)

    print("\n✅  Done\n")


if __name__ == "__main__":
    main()

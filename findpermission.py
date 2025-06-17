#!/usr/bin/env python3
"""
list_permissions.py
~~~~~~~~~~~~~~~~~~~
Print every effective IAM permission a Google Cloud principal receives
inside one project / folder / organisation.

Usage
-----
    python list_permissions.py \
        user:alice@example.com \
        my-project-id

Positional arguments
--------------------
1. principal   The identity to inspect
               (user:… | group:… | serviceAccount:… | etc.)
2. scope_id    A Project-ID, Folder-ID, or Organisation-ID.
               The script auto-prepends the right prefix.
               Examples:
                 "my-project-id"         → scope = projects/my-project-id
                 "123456789012" (folder) → scope = folders/123456789012
                 "876543210987" (org)    → scope = organizations/876543210987
"""

from __future__ import annotations
import argparse
from collections import defaultdict
from typing import Iterable, Set

from google.cloud import asset_v1                # pip install google-cloud-asset
from google.cloud.iam_admin_v1 import IAMClient  # pip install google-cloud-iam
from google.api_core.exceptions import NotFound

# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────
def normalize_scope(raw: str) -> str:
    """Add the correct Resource-Manager prefix if the caller omitted it."""
    if raw.startswith(("projects/", "folders/", "organizations/")):
        return raw
    if raw.isdigit() and len(raw) == 12:         # crude folder / org heuristic
        return f"folders/{raw}"
    return f"projects/{raw}"                     # default to project


def find_roles(principal: str, scope: str) -> Set[str]:
    """Return every distinct role string that contains the principal."""
    asset_client = asset_v1.AssetServiceClient()
    query = f'policy:"{principal}"'
    pager = asset_client.search_all_iam_policies(
        request={"scope": scope, "query": query}
    )
    roles: Set[str] = set()
    for result in pager:
        # Each result is google.cloud.asset_v1.types.IamPolicySearchResult
        for b in result.policy.bindings:
            if principal in b.members:
                roles.add(b.role)
    return roles


def expand_permissions(role: str, iam_client: IAMClient) -> Iterable[str]:
    """Yield every permission in the role."""
    # Predefined vs custom roles both work with get_role(name=role_full_path)
    try:
        role_obj = iam_client.get_role(request={"name": role})
        yield from role_obj.included_permissions
    except NotFound:
        # Small fraction of old predefined roles live under
        # organizations/…/roles/… → fall back to /roles/… path if needed
        if not role.startswith("roles/"):
            short = role.split("/")[-1]
            try:
                role_obj = iam_client.get_role(request={"name": f"roles/{short}"})
                yield from role_obj.included_permissions
            except NotFound:
                print(f"⚠️  skipped unknown role {role}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump every IAM permission a principal has in the given scope."
    )
    parser.add_argument("principal", help='e.g.  user:alice@example.com')
    parser.add_argument("scope_id",  help='Project-ID | Folder-ID | Organisation-ID')
    args = parser.parse_args()

    scope = normalize_scope(args.scope_id)
    iam_client = IAMClient()

    print(f"\n🔎  Searching IAM policies under {scope!r} for {args.principal!r} …")
    roles = find_roles(args.principal, scope)

    if not roles:
        print("🙅  No roles found.")
        return

    print(f"🗂️   {len(roles)} distinct roles → expanding to permissions …\n")

    total_perms: set[str] = set()
    for role in sorted(roles):
        perms = set(expand_permissions(role, iam_client))
        total_perms |= perms
        print(f"# {role}  ({len(perms)} permissions)")
        for p in sorted(perms):
            print(f"  • {p}")
        print()

    print("═════════════════════════════════════════════════════════════")
    print(f"✅  {args.principal} has {len(total_perms)} unique permissions "
          f"in {scope}\n")


if __name__ == "__main__":
    main()

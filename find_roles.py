# list_my_roles.py  –  reads the same IAM table you see in the Console
from google.auth import default
from google.cloud import resourcemanager_v3

creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
client   = resourcemanager_v3.ProjectsClient(credentials=creds)

PROJECT   = "cig-accounting-dev-1"
PRINCIPAL = "user:jalaj.mehta@citadel.com"

policy = client.get_iam_policy(request={"resource": f"projects/{PROJECT}"})
roles  = {b.role for b in policy.bindings if PRINCIPAL in b.members}

print("\nRoles for", PRINCIPAL, "in", PROJECT)
for r in sorted(roles):
    print(" •", r)

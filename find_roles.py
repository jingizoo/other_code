from google.cloud import resourcemanager_v3
from google.oauth2 import service_account   # OR use ADC if you run as yourself

creds   = service_account.Credentials.from_service_account_file("key.json")
client  = resourcemanager_v3.ProjectsClient(credentials=creds)
policy  = client.get_iam_policy(request={"resource": "projects/cig-accounting-dev-1"})

principal = "user:jalaj.mehta@citadel.com"
roles = {b.role for b in policy.bindings if principal in b.members}
print("\nRoles for", principal)
for r in sorted(roles):
    print(" •", r)

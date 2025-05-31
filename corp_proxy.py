# proxy_setup.py
import os, pathlib

PROXY   = "http://proxy.company.local:8080"
NO_PROXY_EXTRA = "googleapis.com,citadelgroup.com"
CA_PEM = pathlib.Path(__file__).with_name("corp_root_ca.pem")  # alongside this file

def enable_corp_proxy():
    os.environ.setdefault("HTTP_PROXY", PROXY)
    os.environ.setdefault("HTTPS_PROXY", PROXY)

    current_no_proxy = os.environ.get("NO_PROXY", "")
    if "googleapis.com" not in current_no_proxy:
        os.environ["NO_PROXY"] = (
            f"{current_no_proxy},{NO_PROXY_EXTRA}" if current_no_proxy else NO_PROXY_EXTRA
        )

    # Trust the corporate root CA
    os.environ.setdefault("REQUESTS_CA_BUNDLE", str(CA_PEM))
    os.environ.setdefault("SSL_CERT_FILE",      str(CA_PEM))

# ------------------------------------------------------------------
# consume in any script *before* you import google-cloud libraries
# ------------------------------------------------------------------
if __name__ == "__main__":
    enable_corp_proxy()
    from google.cloud import storage
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(r"C:\keys\svc.json")
    client = storage.Client(credentials=creds)
    print([b.name for b in client.list_blobs("my-bucket")])

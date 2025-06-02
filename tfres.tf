resource "google_bigquery_dataset" "peoplesoft_archive" {
  dataset_id                 = "peoplesoft_archive"
  project                    = var.project_id          # or hard-code
  location                   = "US"                    # e.g. US, EU, asia-south1…
  description                = "PeopleSoft archive tables"
  default_table_expiration_ms = 90 * 24 * 60 * 60 * 1000  # 90 days (optional)

  # Safety net: don’t let ‘terraform destroy’ drop the data by mistake
  delete_contents_on_destroy = false

  labels = {
    env  = var.env         # dev, qa, prod …
    team = "accounting"
  }
}

terraform import \
  google_bigquery_dataset.peoplesoft_archive \
  cig-accounting-dev-1:peoplesoft_archive

terraform show -json tfplan.bin \
  | jq -r '
      .resource_changes[]
      | select(.change.actions | index("delete"))
      | .address'

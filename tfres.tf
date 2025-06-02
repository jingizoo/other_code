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
###############################################################################
# Auto-import for the existing BigQuery dataset
###############################################################################
import {
  # --- real-world ID Terraform expects ---
  # Format: <PROJECT_ID>:<DATASET_ID>
  id = "cig-accounting-dev-1:peoplesoft_archive"

  # --- where in your config it should live ---
  to = google_bigquery_dataset.peoplesoft_archive
}

###############################################################################
# Auto-import for the existing Concur GCS bucket created outside TF
###############################################################################
import {
  # ID format for buckets when using the Google provider
  id = "projects/_/buckets/cig-concur-dev"

  # Resource address *inside the module*:
  # module.<MODULE NAME>.<RESOURCE TYPE>.<NAME>
  to = module.gcs_storage_bucket_concur.google_storage_bucket.gcs_bucket
}

# ─────────────────────────────────────────────────────────────────────────────
# Nothing else changes in your module block; keep the bucket definition exactly
# as you have it so the configuration matches after import.
# ─────────────────────────────────────────────────────────────────────────────
module "gcs_storage_bucket_concur" {
  source                     = "artifactory.citadelgroup.com/pe-terraform-local__platform-engineering/gcs_storage_bucket/google"
  version                    = "~> 2.3"

  name                       = "cig-concur-dev"
  project                    = local.project
  location                   = "NAM4"

  soft_delete_retention_days = 0
  data_type                  = "app-data"
  ttl                        = 30

  versioning = {
    enabled           = true
    max_object_versions = 2
    non_current_ttl     = 15
  }

  extra_labels = {}
}

# ----- 1) stand-alone buckets declared directly in main.tf ----------
terraform import google_storage_bucket.peoplesoft-cold-storage-archieve \
  projects/_/buckets/peoplesoft-cold-storage-archieve

terraform import google_storage_bucket.cig-accounting-opkey-dev-data-1 \
  projects/_/buckets/cig-accounting-opkey-dev-data-1


# ----- 2) buckets created *inside* the two modules ------------------
terraform import module.gcs_storage_bucket_concur.google_storage_bucket.gcs_bucket \
  projects/_/buckets/cig-concur-dev

terraform import module.gcs_storage_bucket_blackline.google_storage_bucket.gcs_bucket \
  projects/_/buckets/cig-blackline-dev


# ----- 3) BigQuery dataset ------------------------------------------
terraform import google_bigquery_dataset.peoplesoft_archive \
  cig-accounting-dev-1:peoplesoft_archive

**Subject:** PeopleSoft → GCP Archiving: Dev Reconciliation Clean ✅ | Request to Proceed with Prod

Hi Everyone,

The first end-to-end archive cycle for the **CIG-Accounting *Dev*** environment is wrapped up and the reconciliation report came back *clean*—no missing rows, no count mismatches. 🎉
You’ll find the recon workbook attached, along with a short explainer of the validation logic.

---

### What’s now available for your review

| Item                                                                                             | Link                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Terraform & upload utilities** (branch `peoplesoft-archive/psdata-cold-storage-upload-and-tf`) | [https://github.com/citadel-am/citsource/tree/jm/psdata-partition-recon-fix/terraform/gcp/pte/accounting/src/main/terraform/cig-accounting-dev-1--base](https://github.com/citadel-am/citsource/tree/jm/psdata-partition-recon-fix/terraform/gcp/pte/accounting/src/main/terraform/cig-accounting-dev-1--base)                                                                       |
| **Python ETL code**                                                                              | [https://github.com/citadel-am/citsource/tree/jm/psdata-partition-recon-fix/pte/accounting/external-services/acctgateway/data-mesh/psdata/peoplesoft\_data\_archive/src/main/python/psdata](https://github.com/citadel-am/citsource/tree/jm/psdata-partition-recon-fix/pte/accounting/external-services/acctgateway/data-mesh/psdata/peoplesoft_data_archive/src/main/python/psdata) |
| **Tableau dashboard** (row counts, partition sizes, runtime stats)                               | [https://tableau.citadelgroup.com/t/PeopleSoft/views/citadel\_peoplesoft\_archived\_reports/Dashboard1](https://tableau.citadelgroup.com/t/PeopleSoft/views/citadel_peoplesoft_archived_reports/Dashboard1)                                                                                                                                                                          |
| **Design/Wiki page**                                                                             | [https://wiki.citadelgroup.com/spaces/PSFINKB/pages/1173825572/Parquet+Exporter+for+PeopleSoft+SQL+Server+Cloud+Storage](https://wiki.citadelgroup.com/spaces/PSFINKB/pages/1173825572/Parquet+Exporter+for+PeopleSoft+SQL+Server+Cloud+Storage)                                                                                                                                     |

---

### Next steps

1. **Peer sign-off**
   *Please skim the attached reconciliation workbook and ping me if you spot anything odd by **tomorrow EOD**.*

2. **Promote to Prod**

   * Once I get the thumbs-up, I’ll replicate the same Terraform state, ETL config, and monitoring setup in the **Production** project.
   * I’ll also refresh the Tableau workbook to point at the prod Parquet buckets.

3. **Final validation**

   * After the initial prod run, we’ll rerun the recon script and circulate the report for a quick sanity check.

---

Let me know if you need anything clarified. Thanks in advance for the quick review so we can keep the prod timeline on track.

Best,
*Your Name*
PeopleSoft | Data & Cloud Engineering

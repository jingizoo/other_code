Below is a lightweight, “getting‑started” wiki page you can drop straight into Confluence, SharePoint, or a Markdown‑compatible repository. It focuses on the single most important task—**finding and selecting the right table or psquery**—and then walks users through the minimal steps needed to explore data or build a new workbook. Feel free to extend each section with screenshots, data‑governance links, or contact names that are specific to your environment.

---

## 1  |  Purpose

This page explains how any analyst or business user can:

1. Locate one of the **≈ 4,000 published data sources** (tables and pre‑built psqueries) on Tableau Cloud.
2. Connect to those sources—whether live in Google BigQuery or materialised on Tableau.
3. Explore, filter and prompt on the data, or build new visualisations and dashboards.

> **Scope** – We assume the data sources are already certified, published, and refreshable; this guide does not cover creating new extracts or advanced modelling.

---

## 2  |  Prerequisites

| Item                  | Details                                                                                                                    |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Tableau Cloud licence | You must be in the *PeopleSoft Archive Reporting* project or a child project.                                              |
| BigQuery entitlement  | If you need to run live SQL against BigQuery (psqueries), you must have Viewer or higher on the *cig‑accounting* datasets. |
| Browser               | Tableau Cloud fully supports Chrome, Edge and modern Firefox.                                                              |

---

## 3  |  Navigation Cheat‑Sheet

| Step | What to Click                                                     | Why                                                             |
| ---- | ----------------------------------------------------------------- | --------------------------------------------------------------- |
| 1    | **Explore  ›  Default  ›  PeopleSoft Archive Reporting**          | Opens the project that hosts all certified sources.             |
| 2    | Set **Content Type = All** and **Sort By = Name** (or *Type*)     | Enables quick alphabetical scan or grouping by connection type. |
| 3    | **Search box** – type a keyword (e.g. *JEDETAIL* or *AP\_VENDOR*) | Instant filter across \~4 k assets.                             |
| 4    | **Filter  ›  Certified** (optional)                               | Limits list to governed data only.                              |
| 5    | Hover a data source tile  ›  click **i**                          | Shows owner, refresh schedule, and fields.                      |
| 6    | Click the thumbnail or name                                       | Opens the sheet preview or launches the **Data Details** pane.  |

> **Tip** – Star (☆) frequently used sources so they surface under **Explore › Favorites**.

---

## 4  |  Understanding the Naming Convention

| Prefix    | Meaning                                            | Example                      |
| --------- | -------------------------------------------------- | ---------------------------- |
| **psq\_** | Pre‑built PeopleSoft *psquery* exposed in BigQuery | `psq_GL_JEDETAIL_FXTRANS_V3` |
| **cig\_** | Consolidated/curated tables owned by Finance BI    | `cig_VENDOR_BANK_UK`         |
| **dw\_**  | Raw Data Warehouse tables                          | `dw_AP_ACTUALS`              |
| **tmp\_** | Sandbox or ad‑hoc extracts (not governed)          | `tmp_JALAJ_TEST_2025Q1`      |

Always prefer *psq\_* or *cig\_* objects—they are column‑renamed and business‑ready.

---

## 5  |  Connecting to Data in a New Workbook

1. From **Explore**, hover the desired source  ›  **⚙ Actions  ›  New Workbook**.
   *A blank sheet opens with the data already in the Data Pane.*

2. **OR** start in an existing workbook and add a source:

   * **Data  ›  New Data Source** → *Connect to Data* dialog appears.
   * **On This Site** tab shows the same searchable list (you can filter by *Connection Type = Google BigQuery*).
   * Select the table / psquery → **Connect**.

3. Verify **Live vs Extract** (icon under the source name).

   * Live = direct BigQuery query (recommended for < 1 M rows or frequent updates).
   * Extract = cached on Tableau Cloud (faster for very wide or static data).

---

## 6  |  Exploring & Prompting the Data

| Technique             | How to Do It                                      | Typical Use                                              |
| --------------------- | ------------------------------------------------- | -------------------------------------------------------- |
| **Data Details pane** | Sheet toolbar → **Data Details**                  | Field list, row count, last refresh, lineage.            |
| **Show Filter**       | Right‑click any discrete field → *Show Filter*    | Quick‑pick prompts (Fiscal Year, Business Unit).         |
| **Ask Data (NLP)**    | Source → **••• ›  Ask Data**                      | Type *“total monetary amount by account for FY 2024”*.   |
| **Parameters**        | **Data  ›  New Parameter** (string, list)         | User‑driven prompts (e.g. choose *Currency Code*).       |
| **Group/Hierarchy**   | Drag fields on top of each other in the Data Pane | Drill‑down (Account » Subaccount).                       |
| **Describe**          | Right‑click field → *Describe*                    | Shows SQL data type + distinct values (handy for audit). |

---

## 7  |  Building a Simple Viz in 90 Seconds

1. In **Columns** drop *Fiscal Year*; in **Rows** drop *Business Unit*.
2. Drag **SUM(Monetary Amount)** to **Text** (Marks card) for a cross‑tab.
3. Right‑click **Fiscal Year** header → *Show Filter* for an interactive year prompt.
4. Switch **Marks** from *Automatic* to *Bar* and adjust sort for a quick bar chart.
5. Click **Dashboard  ›  New Dashboard**, drag your sheet, save.

---

## 8  |  Performance & Cost Tips

| Tip                                                       | Why It Matters                                       |
| --------------------------------------------------------- | ---------------------------------------------------- |
| Use **Extracts** for wide historical tables (> 10 M rows) | Reduces BigQuery costs and speeds dashboards.        |
| Keep filters selective (Business Unit, Fiscal Year)       | BigQuery bills per scanned byte.                     |
| Limit custom SQL                                          | Tableau wraps it in nested queries that can be slow. |
| Leverage **Data Source Filters** over worksheet filters   | Applies at query time, not post‑aggregation.         |

---

## 9  |  FAQ

| Question                                                       | Answer                                                                                                              |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **I can’t see a table I need.**                                | It may reside in a different project or is unpublished. Use Global Search or ask the data owner to publish/certify. |
| **How do I get column definitions?**                           | Hover the field in the Data Pane (tooltip) or click *i* on the source tile to view the business glossary link.      |
| **The preview shows “Live Connection” but I need a snapshot.** | In the Data Source tab choose **Extract  ›  Create Local Copy** → *Publish as Extract*.                             |
| **Why is my query slow?**                                      | Check the *Performance Recording* (Help › Settings and Performance) or view BigQuery job cost in GCP console.       |

---

## 10  |  Need Help?

| Topic                              | Contact / Channel                                     |
| ---------------------------------- | ----------------------------------------------------- |
| Data quality, new psquery requests | **Finance BI – Data Engineering** (Slack #bi-finance) |
| Access & permissions               | **IT Service Desk**                                   |
| Tableau best practices             | **Analytics CoE** – weekly office hours               |

---

### Revision History

| Date       | Author      | Change             |
| ---------- | ----------- | ------------------ |
| 2025‑06‑11 | Jalaj Mehta | Initial wiki draft |

---

**Copy & paste** this markup into your wiki platform, add a few screenshots (e.g., the *Connect to Data* dialog and a sample sheet), and you’ll have a concise but complete reference that steers users straight to the correct tables and psqueries without drowning them in detail.

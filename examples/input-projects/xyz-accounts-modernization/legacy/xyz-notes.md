# XYZ Notes

- XYZ is the current system of record for Accounts.
- CRM sends JSON CRUD requests.
- XYZ populates `acct_staging_tbl` for ETL during EOD flows.
- The first MVP should preserve the CRM-facing API and staging-table handoff behavior.

CREATE TABLE account_staging_tbl (
    staging_row_id VARCHAR(36) NOT NULL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    business_date DATE NOT NULL,
    staging_status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP,
    account_id VARCHAR(36),
    account_number VARCHAR(12) NOT NULL,
    opened_date DATE NOT NULL,
    available_balance DECIMAL(19,4) NOT NULL
);

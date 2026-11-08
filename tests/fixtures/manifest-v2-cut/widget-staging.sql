CREATE TABLE widget_staging (
    staging_row_id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    business_date DATE NOT NULL,
    staging_status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    widget_id VARCHAR(36) NOT NULL,
    payload_key VARCHAR(64) NOT NULL
);

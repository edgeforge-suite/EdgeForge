CREATE TABLE settlement_stage (
    international_payment_id VARCHAR(40) NOT NULL,
    consent_id VARCHAR(128) NOT NULL,
    instruction_identification VARCHAR(35) NOT NULL,
    end_to_end_identification VARCHAR(35) NOT NULL,
    currency_of_transfer CHAR(3) NOT NULL,
    instructed_amount DECIMAL(18,2) NOT NULL,
    creditor_name VARCHAR(70) NOT NULL,
    payment_status VARCHAR(40) NOT NULL,
    status_update_ts TIMESTAMP NOT NULL
);

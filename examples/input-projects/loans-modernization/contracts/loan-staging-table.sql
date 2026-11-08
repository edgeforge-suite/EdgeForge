CREATE TABLE loan_staging (
    loan_id          VARCHAR(20)    NOT NULL,
    borrower_id      VARCHAR(20)    NOT NULL,
    principal_amount DECIMAL(19,4)  NOT NULL,
    interest_rate    DECIMAL(9,6)   NOT NULL,
    term_months      INTEGER        NOT NULL,
    loan_type        VARCHAR(10)    NOT NULL,
    status           VARCHAR(20)    NOT NULL,
    purpose          VARCHAR(200),
    created_at       TIMESTAMP      NOT NULL
);

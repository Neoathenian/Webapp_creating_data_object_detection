-- Database schema for authentication, credit ledger, and API key management
-- Target platform: PostgreSQL 13+

BEGIN;

CREATE TABLE IF NOT EXISTS app_user (
    id SERIAL PRIMARY KEY,
    oauth_sub VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS payment (
    provider VARCHAR(32) NOT NULL,
    provider_event_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    amount_cents BIGINT NOT NULL,
    credits_granted BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL
);
CREATE INDEX IF NOT EXISTS payment_user_idx ON payment (user_id);
CREATE INDEX IF NOT EXISTS payment_status_idx ON payment (status);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    delta BIGINT NOT NULL,
    reason VARCHAR(255) NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ledger_source UNIQUE (source_type, source_id),
    CONSTRAINT ck_credit_ledger_delta_nonzero CHECK (delta <> 0)
);
CREATE INDEX IF NOT EXISTS ix_ledger_user_created ON credit_ledger (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_balance (
    user_id INTEGER PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
    balance BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_api_key (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    key_hash VARCHAR(128) NOT NULL UNIQUE,
    key_prefix VARCHAR(32) NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    storage_uid VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT ux_user_api_key_user_prefix UNIQUE (user_id, key_prefix)
);
CREATE INDEX IF NOT EXISTS ix_user_api_key_storage_uid ON user_api_key (storage_uid);
CREATE INDEX IF NOT EXISTS ix_user_api_key_user ON user_api_key (user_id);

COMMIT;

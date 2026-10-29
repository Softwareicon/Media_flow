BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_initial

CREATE TABLE users (
    id VARCHAR(36) NOT NULL, 
    email VARCHAR(320), 
    password_hash TEXT, 
    is_anonymous BOOLEAN NOT NULL, 
    keep_server_history BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE TABLE sessions (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_used_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE oauth_connections (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    platform VARCHAR(32) NOT NULL, 
    access_token_enc TEXT NOT NULL, 
    refresh_token_enc TEXT, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    scope TEXT, 
    external_account_id VARCHAR(128), 
    external_username VARCHAR(256), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_connection_user_platform UNIQUE (user_id, platform), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_oauth_connections_user_id ON oauth_connections (user_id);

CREATE TABLE oauth_states (
    state_hash VARCHAR(64) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    platform VARCHAR(32) NOT NULL, 
    code_verifier VARCHAR(128), 
    handoff_hash VARCHAR(64), 
    token_payload_enc TEXT, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (state_hash), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (handoff_hash)
);

CREATE TABLE media_analyses (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    source_url TEXT NOT NULL, 
    platform VARCHAR(32) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    result JSON NOT NULL, 
    private JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_media_analyses_user_id ON media_analyses (user_id);

CREATE INDEX ix_media_analyses_expires_at ON media_analyses (expires_at);

CREATE TABLE downloads (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    analysis_id VARCHAR(36), 
    platform VARCHAR(32) NOT NULL, 
    source_url TEXT NOT NULL, 
    title TEXT, 
    option_id VARCHAR(64) NOT NULL, 
    quality_label VARCHAR(64), 
    mime_type VARCHAR(64) NOT NULL, 
    file_name VARCHAR(128) NOT NULL, 
    expected_bytes BIGINT, 
    received_bytes BIGINT, 
    status VARCHAR(16) NOT NULL, 
    error_code VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(analysis_id) REFERENCES media_analyses (id) ON DELETE SET NULL
);

CREATE INDEX ix_downloads_user_created ON downloads (user_id, created_at);

INSERT INTO alembic_version (version_num) VALUES ('0001_initial') RETURNING alembic_version.version_num;

COMMIT;


-- DARIO Orchestrator Runtime — Initial Schema
-- Database: dario_kb (shared with RAG engine)
-- Schema: orch (separate from kb)

CREATE SCHEMA IF NOT EXISTS orch;

-- Operational state (singleton)
CREATE TABLE IF NOT EXISTS orch.operational_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    state VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    autonomy_level VARCHAR(10) NOT NULL DEFAULT 'P-A1',
    system_health FLOAT NOT NULL DEFAULT 0.85,
    fitness_score FLOAT NOT NULL DEFAULT 0.0,
    max_parallel INTEGER NOT NULL DEFAULT 3,
    generation INTEGER NOT NULL DEFAULT 1,
    total_tasks_completed INTEGER NOT NULL DEFAULT 0,
    last_state_change TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_pulse TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tasks mirror
CREATE TABLE IF NOT EXISTS orch.tasks (
    id VARCHAR(30) PRIMARY KEY,
    title TEXT NOT NULL,
    project VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'backlog',
    priority VARCHAR(20) DEFAULT 'normal',
    assignee VARCHAR(100),
    skill VARCHAR(100),
    division VARCHAR(50),
    estimated_tokens INTEGER,
    actual_tokens INTEGER,
    quality_score FLOAT,
    execution_policy VARCHAR(30),
    depends_on TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON orch.tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON orch.tasks(project);

-- Quality scores
CREATE TABLE IF NOT EXISTS orch.quality_scores (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(30),
    skill VARCHAR(100) NOT NULL,
    project VARCHAR(100),
    specificity FLOAT NOT NULL DEFAULT 0,
    actionability FLOAT NOT NULL DEFAULT 0,
    completeness FLOAT NOT NULL DEFAULT 0,
    accuracy FLOAT NOT NULL DEFAULT 0,
    tone FLOAT NOT NULL DEFAULT 0,
    composite_score FLOAT NOT NULL DEFAULT 0,
    weights_used JSONB,
    confidence_mode VARCHAR(20),
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quality_scored_at ON orch.quality_scores(scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_skill ON orch.quality_scores(skill);

-- Mutations log
CREATE TABLE IF NOT EXISTS orch.mutations (
    id SERIAL PRIMARY KEY,
    generation INTEGER NOT NULL,
    file_mutated VARCHAR(300) NOT NULL,
    field_changed VARCHAR(300) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 0.5,
    fitness_before FLOAT,
    fitness_after FLOAT,
    status VARCHAR(20) NOT NULL DEFAULT 'applied',
    tasks_since_applied INTEGER DEFAULT 0,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evaluated_at TIMESTAMPTZ
);

-- Evolution journal
CREATE TABLE IF NOT EXISTS orch.evolution_journal (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50),
    pulse_type VARCHAR(20) NOT NULL,
    tasks_completed INTEGER DEFAULT 0,
    avg_quality FLOAT,
    skills_used JSONB,
    skill_pairs JSONB,
    fallbacks_triggered INTEGER DEFAULT 0,
    user_corrections INTEGER DEFAULT 0,
    patterns_detected JSONB,
    evolutionary_delta FLOAT,
    generation INTEGER NOT NULL DEFAULT 1,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_journal_recorded_at ON orch.evolution_journal(recorded_at DESC);

-- Fitness history (time series)
CREATE TABLE IF NOT EXISTS orch.fitness_history (
    id SERIAL PRIMARY KEY,
    fitness_score FLOAT NOT NULL,
    avg_quality FLOAT NOT NULL DEFAULT 0,
    budget_ratio FLOAT NOT NULL DEFAULT 0,
    task_velocity FLOAT NOT NULL DEFAULT 0,
    generation INTEGER NOT NULL DEFAULT 1,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fitness_measured_at ON orch.fitness_history(measured_at DESC);

-- Synaptic weights
CREATE TABLE IF NOT EXISTS orch.synaptic_weights (
    id SERIAL PRIMARY KEY,
    skill_a VARCHAR(100) NOT NULL,
    skill_b VARCHAR(100) NOT NULL,
    co_activations INTEGER NOT NULL DEFAULT 0,
    avg_combined_score FLOAT NOT NULL DEFAULT 0,
    weight FLOAT NOT NULL DEFAULT 0.5,
    last_activated TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(skill_a, skill_b)
);

-- Detected patterns
CREATE TABLE IF NOT EXISTS orch.patterns (
    id SERIAL PRIMARY KEY,
    pattern_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    occurrences INTEGER NOT NULL DEFAULT 1,
    threshold INTEGER NOT NULL DEFAULT 5,
    crystallized BOOLEAN NOT NULL DEFAULT FALSE,
    rule_applied TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    crystallized_at TIMESTAMPTZ
);

-- Budget monthly
CREATE TABLE IF NOT EXISTS orch.budget_monthly (
    month VARCHAR(7) PRIMARY KEY,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    token_limit BIGINT NOT NULL DEFAULT 50000000,
    percentage FLOAT NOT NULL DEFAULT 0.0,
    by_project JSONB DEFAULT '{}'::jsonb,
    by_skill JSONB DEFAULT '{}'::jsonb,
    by_model JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log (append-only)
CREATE TABLE IF NOT EXISTS orch.audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_code VARCHAR(100) NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'info',
    entity_type VARCHAR(30),
    entity_id VARCHAR(100),
    details JSONB,
    session_id VARCHAR(50),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_recorded_at ON orch.audit_log(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event ON orch.audit_log(event_code);

-- Initialize operational state
INSERT INTO orch.operational_state (state, autonomy_level, system_health, generation)
VALUES ('ACTIVE', 'P-A1', 0.85, 1)
ON CONFLICT (id) DO NOTHING;

-- Initialize current month budget
INSERT INTO orch.budget_monthly (month, total_tokens, token_limit)
VALUES (TO_CHAR(NOW(), 'YYYY-MM'), 0, 50000000)
ON CONFLICT (month) DO NOTHING;

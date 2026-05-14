CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    CREATE TYPE dataset_name AS ENUM ('mvtec', 'wafer', 'tep');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE review_status AS ENUM ('auto', 'reviewed', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE feedback_target_type AS ENUM (
        'entity_link',
        'correction_candidate',
        'ranked_path',
        'kg_edge',
        'kg_node',
        'case',
        'root_cause_candidate'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TYPE feedback_target_type ADD VALUE IF NOT EXISTS 'case';
ALTER TYPE feedback_target_type ADD VALUE IF NOT EXISTS 'root_cause_candidate';

DO $$
BEGIN
    CREATE TYPE feedback_value AS ENUM ('accept', 'reject', 'edit', 'uncertain');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS datasets (
    dataset dataset_name PRIMARY KEY,
    display_name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO datasets (dataset, display_name, description)
VALUES
    ('mvtec', 'MVTec', 'Image anomaly evidence and plausible visual RCA references.'),
    ('wafer', 'Wafer', 'Wafer map and wafer log anomaly evidence.'),
    ('tep', 'TEP', 'Tennessee Eastman process time-series evidence.')
ON CONFLICT (dataset) DO NOTHING;

CREATE TABLE IF NOT EXISTS source_documents (
    source_id text PRIMARY KEY,
    dataset dataset_name,
    title text NOT NULL,
    source_type text NOT NULL,
    uri text,
    citation text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kg_versions (
    kg_version text PRIMARY KEY,
    imported_at timestamptz NOT NULL DEFAULT now(),
    importer text,
    neo4j_database text NOT NULL DEFAULT 'neo4j',
    scenario_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes text
);

CREATE TABLE IF NOT EXISTS evidence_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id text NOT NULL,
    dataset dataset_name NOT NULL,
    object_name text,
    anomaly_type text,
    source text,
    timestamp timestamptz,
    evidence_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_evidence jsonb NOT NULL,
    normalized_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    human_feedback jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset, case_id)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE SET NULL,
    dataset dataset_name NOT NULL,
    mode text NOT NULL DEFAULT 'evidence',
    source_filename text NOT NULL DEFAULT 'upload',
    top_k integer NOT NULL DEFAULT 5,
    run_dir text NOT NULL DEFAULT '',
    case_count integer NOT NULL DEFAULT 0,
    evidence_count integer NOT NULL DEFAULT 0,
    label text NOT NULL DEFAULT 'Analysis run',
    claim_boundary text NOT NULL DEFAULT 'candidate/plausible explanation only; not a verified root-cause label',
    model_preset text,
    model_backend text,
    kg_version text REFERENCES kg_versions(kg_version),
    pipeline_version text,
    status text NOT NULL DEFAULT 'completed',
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text
);

CREATE TABLE IF NOT EXISTS run_evidence_cases (
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    case_pk uuid NOT NULL REFERENCES evidence_cases(id) ON DELETE CASCADE,
    case_order integer NOT NULL DEFAULT 0,
    generated_evidence_path text,
    adapter_name text,
    PRIMARY KEY (run_id, case_pk)
);

CREATE TABLE IF NOT EXISTS linked_entities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE,
    link_id text NOT NULL,
    field text NOT NULL,
    mention text NOT NULL,
    selected_entity_id text,
    selected_entity_scenario text,
    score double precision NOT NULL DEFAULT 0,
    match_type text NOT NULL,
    ambiguous boolean NOT NULL DEFAULT false,
    candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (run_id, case_pk, link_id)
);

CREATE TABLE IF NOT EXISTS consistency_checks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE,
    consistency_score double precision NOT NULL,
    inconsistent_fields text[] NOT NULL DEFAULT '{}',
    checks jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS correction_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE,
    candidate_id text NOT NULL,
    field text NOT NULL,
    original_value text,
    suggested_value text,
    suggested_entity_id text,
    score double precision NOT NULL DEFAULT 0,
    reason text,
    source_edges jsonb NOT NULL DEFAULT '[]'::jsonb,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, case_pk, candidate_id)
);

CREATE TABLE IF NOT EXISTS ranked_paths (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE,
    path_id text NOT NULL,
    rank integer NOT NULL,
    source_entity_id text,
    target_entity_id text,
    node_ids text[] NOT NULL,
    relation_ids text[] NOT NULL,
    score double precision NOT NULL,
    confidence double precision,
    evidence_match double precision,
    source_edge_ids text[] NOT NULL DEFAULT '{}',
    supporting_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (run_id, case_pk, path_id)
);

CREATE TABLE IF NOT EXISTS feedback_records (
    feedback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset dataset_name NOT NULL,
    run_id uuid REFERENCES analysis_runs(run_id) ON DELETE SET NULL,
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE SET NULL,
    target_type feedback_target_type NOT NULL,
    target_id text NOT NULL,
    feedback feedback_value NOT NULL,
    corrected_value jsonb,
    comment text,
    reviewer text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kg_edit_drafts (
    draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset dataset_name NOT NULL,
    kg_version text REFERENCES kg_versions(kg_version),
    operation text NOT NULL,
    target_type text NOT NULL,
    target_id text,
    draft_payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
);

CREATE TABLE IF NOT EXISTS kg_review_actions (
    action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset dataset_name NOT NULL,
    kg_version text REFERENCES kg_versions(kg_version),
    target_type text NOT NULL,
    target_id text NOT NULL,
    review_status review_status NOT NULL,
    reviewer text,
    comment text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset dataset_name,
    case_pk uuid REFERENCES evidence_cases(id) ON DELETE SET NULL,
    run_id uuid REFERENCES analysis_runs(run_id) ON DELETE SET NULL,
    artifact_type text NOT NULL,
    uri text NOT NULL,
    media_type text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE evidence_cases
    ADD COLUMN IF NOT EXISTS evidence_payload jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE analysis_runs
    ALTER COLUMN case_pk DROP NOT NULL;

ALTER TABLE analysis_runs
    ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'evidence',
    ADD COLUMN IF NOT EXISTS source_filename text NOT NULL DEFAULT 'upload',
    ADD COLUMN IF NOT EXISTS top_k integer NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS run_dir text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS case_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS evidence_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS label text NOT NULL DEFAULT 'Analysis run',
    ADD COLUMN IF NOT EXISTS claim_boundary text NOT NULL DEFAULT 'candidate/plausible explanation only; not a verified root-cause label',
    ADD COLUMN IF NOT EXISTS model_preset text,
    ADD COLUMN IF NOT EXISTS model_backend text;

ALTER TABLE linked_entities
    ADD COLUMN IF NOT EXISTS case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE;

ALTER TABLE consistency_checks
    ADD COLUMN IF NOT EXISTS case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE;

ALTER TABLE correction_candidates
    ADD COLUMN IF NOT EXISTS case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE;

ALTER TABLE ranked_paths
    ADD COLUMN IF NOT EXISTS case_pk uuid REFERENCES evidence_cases(id) ON DELETE CASCADE;

ALTER TABLE linked_entities
    DROP CONSTRAINT IF EXISTS linked_entities_run_id_link_id_key;
ALTER TABLE correction_candidates
    DROP CONSTRAINT IF EXISTS correction_candidates_run_id_candidate_id_key;
ALTER TABLE ranked_paths
    DROP CONSTRAINT IF EXISTS ranked_paths_run_id_path_id_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'linked_entities_run_case_link_key'
    ) THEN
        ALTER TABLE linked_entities
            ADD CONSTRAINT linked_entities_run_case_link_key UNIQUE (run_id, case_pk, link_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'correction_candidates_run_case_candidate_key'
    ) THEN
        ALTER TABLE correction_candidates
            ADD CONSTRAINT correction_candidates_run_case_candidate_key
            UNIQUE (run_id, case_pk, candidate_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ranked_paths_run_case_path_key'
    ) THEN
        ALTER TABLE ranked_paths
            ADD CONSTRAINT ranked_paths_run_case_path_key UNIQUE (run_id, case_pk, path_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_cases_dataset_case
    ON evidence_cases(dataset, case_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_case
    ON analysis_runs(case_pk, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_dataset
    ON analysis_runs(dataset, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_evidence_cases_run
    ON run_evidence_cases(run_id, case_order);
CREATE INDEX IF NOT EXISTS idx_linked_entities_run
    ON linked_entities(run_id);
CREATE INDEX IF NOT EXISTS idx_linked_entities_case
    ON linked_entities(case_pk);
CREATE UNIQUE INDEX IF NOT EXISTS idx_linked_entities_run_case_link_unique
    ON linked_entities(run_id, case_pk, link_id);
CREATE INDEX IF NOT EXISTS idx_consistency_checks_run
    ON consistency_checks(run_id);
CREATE INDEX IF NOT EXISTS idx_consistency_checks_case
    ON consistency_checks(case_pk);
CREATE INDEX IF NOT EXISTS idx_correction_candidates_run
    ON correction_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_correction_candidates_case
    ON correction_candidates(case_pk);
CREATE UNIQUE INDEX IF NOT EXISTS idx_correction_candidates_run_case_candidate_unique
    ON correction_candidates(run_id, case_pk, candidate_id);
CREATE INDEX IF NOT EXISTS idx_ranked_paths_run_rank
    ON ranked_paths(run_id, rank);
CREATE INDEX IF NOT EXISTS idx_ranked_paths_case_rank
    ON ranked_paths(case_pk, rank);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ranked_paths_run_case_path_unique
    ON ranked_paths(run_id, case_pk, path_id);
CREATE INDEX IF NOT EXISTS idx_feedback_target
    ON feedback_records(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_feedback_run
    ON feedback_records(run_id);
CREATE INDEX IF NOT EXISTS idx_kg_review_target
    ON kg_review_actions(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run
    ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_raw_gin
    ON evidence_cases USING gin(raw_evidence);
CREATE INDEX IF NOT EXISTS idx_evidence_normalized_gin
    ON evidence_cases USING gin(normalized_evidence);

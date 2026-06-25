-- =============================================================================
-- Postgres storage v8 — idempotent application
-- =============================================================================
-- This file is generated from the raw pg_dump output by
-- scripts/normalize_migration_008.py and is expected to be replayable
-- against any state (empty, partial, fully applied). It does NOT use the
-- pg_dump paste-blocker ``\restrict`` macro and strips session-level SET
-- statements so psql -f and CI replay tooling both work.
--
-- Original raw dump preserved alongside as
-- 008_postgres_storage_v8.sql.original for forensic purposes.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner:
COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner:
COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';
-- Name: idempotency_keys; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.idempotency_keys (
    idem_key text NOT NULL,
    job_id text NOT NULL,
    request_fingerprint text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.idempotency_keys OWNER TO dataforge';
   END IF;
END $$;
-- Name: job_events; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.job_events (
    event_id bigint NOT NULL,
    job_id text NOT NULL,
    "timestamp" text DEFAULT ''::text NOT NULL,
    level text DEFAULT 'info'::text NOT NULL,
    message text NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.job_events OWNER TO dataforge';
   END IF;
END $$;
-- Name: job_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: dataforge
CREATE SEQUENCE IF NOT EXISTS public.job_events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER SEQUENCE public.job_events_event_id_seq OWNER TO dataforge';
   END IF;
END $$;
-- Name: job_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dataforge
ALTER SEQUENCE public.job_events_event_id_seq OWNED BY public.job_events.event_id;
-- Name: job_results; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.job_results (
    job_id text NOT NULL,
    result_index integer NOT NULL,
    payload text NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.job_results OWNER TO dataforge';
   END IF;
END $$;
-- Name: jobs; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.jobs (
    id text NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    mode text DEFAULT 'manual'::text,
    topic text DEFAULT ''::text,
    intent text DEFAULT ''::text,
    urls text DEFAULT '[]'::text,
    schema_fields text DEFAULT '[]'::text,
    filters text DEFAULT '[]'::text,
    results text DEFAULT '[]'::text,
    logs text DEFAULT '[]'::text,
    total_records integer DEFAULT 0,
    filtered_records integer DEFAULT 0,
    total_llm_calls integer DEFAULT 0,
    error text DEFAULT ''::text,
    warnings text DEFAULT ''::text,
    quality_report text DEFAULT '{}'::text,
    analysis text DEFAULT ''::text,
    discovered_urls text DEFAULT '[]'::text,
    selectors_map text DEFAULT '{}'::text,
    search_params text DEFAULT '{}'::text,
    max_pages integer DEFAULT 0,
    progress_current integer DEFAULT 0,
    progress_total integer DEFAULT 0,
    estimated_cost_usd real DEFAULT 0,
    cancel_requested boolean DEFAULT false,
    created_by text DEFAULT ''::text,
    org_id text DEFAULT ''::text,
    project_id text DEFAULT ''::text,
    created_at text DEFAULT ''::text,
    completed_at text DEFAULT ''::text,
    min_record_score real DEFAULT 0.35,
    acquisition_mode text DEFAULT 'standard'::text,
    location text DEFAULT ''::text,
    preferred_domain text DEFAULT ''::text,
    source_policy text DEFAULT 'all_sources'::text,
    max_per_domain integer DEFAULT 4,
    origin_location text DEFAULT ''::text,
    max_distance_km real,
    pagination boolean DEFAULT false,
    deduplicate boolean DEFAULT true,
    deduplicate_field text DEFAULT ''::text,
    started_at text DEFAULT ''::text,
    results_on_disk boolean DEFAULT false,
    results_file_path text DEFAULT ''::text,
    updated_at text DEFAULT ''::text,
    deleted_at text
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.jobs OWNER TO dataforge';
   END IF;
END $$;
-- Name: queue_schema_version; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.queue_schema_version (
    id integer NOT NULL,
    version integer NOT NULL,
    CONSTRAINT queue_schema_version_id_check CHECK ((id = 1))
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.queue_schema_version OWNER TO dataforge';
   END IF;
END $$;
-- Name: queue_task_history; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.queue_task_history (
    id text NOT NULL,
    type text NOT NULL,
    payload text DEFAULT '{}'::text NOT NULL,
    priority integer DEFAULT 2 NOT NULL,
    status text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    attempts integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    last_error text,
    timeout_seconds integer DEFAULT 300 NOT NULL,
    finished_at timestamp without time zone DEFAULT now() NOT NULL,
    result text,
    execution_time_ms integer
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.queue_task_history OWNER TO dataforge';
   END IF;
END $$;
-- Name: queue_tasks; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.queue_tasks (
    id text NOT NULL,
    type text NOT NULL,
    payload text DEFAULT '{}'::text NOT NULL,
    priority integer DEFAULT 2 NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    attempts integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    last_error text,
    scheduled_at timestamp without time zone DEFAULT now() NOT NULL,
    timeout_seconds integer DEFAULT 300 NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.queue_tasks OWNER TO dataforge';
   END IF;
END $$;
-- Name: rate_limits; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.rate_limits (
    key character varying(255) NOT NULL,
    "timestamp" double precision NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.rate_limits OWNER TO dataforge';
   END IF;
END $$;
-- Name: recycle_bin; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.recycle_bin (
    id text NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    mode text DEFAULT 'manual'::text,
    topic text DEFAULT ''::text,
    intent text DEFAULT ''::text,
    urls text DEFAULT '[]'::text,
    schema_fields text DEFAULT '[]'::text,
    filters text DEFAULT '[]'::text,
    results text DEFAULT '[]'::text,
    logs text DEFAULT '[]'::text,
    total_records integer DEFAULT 0,
    filtered_records integer DEFAULT 0,
    total_llm_calls integer DEFAULT 0,
    error text DEFAULT ''::text,
    warnings text DEFAULT ''::text,
    quality_report text DEFAULT '{}'::text,
    analysis text DEFAULT ''::text,
    discovered_urls text DEFAULT '[]'::text,
    selectors_map text DEFAULT '{}'::text,
    search_params text DEFAULT '{}'::text,
    max_pages integer DEFAULT 0,
    progress_current integer DEFAULT 0,
    progress_total integer DEFAULT 0,
    estimated_cost_usd real DEFAULT 0,
    cancel_requested boolean DEFAULT false,
    created_by text DEFAULT ''::text,
    org_id text DEFAULT ''::text,
    project_id text DEFAULT ''::text,
    created_at text DEFAULT ''::text,
    completed_at text DEFAULT ''::text,
    min_record_score real DEFAULT 0.35,
    acquisition_mode text DEFAULT 'standard'::text,
    location text DEFAULT ''::text,
    preferred_domain text DEFAULT ''::text,
    source_policy text DEFAULT 'all_sources'::text,
    max_per_domain integer DEFAULT 4,
    origin_location text DEFAULT ''::text,
    max_distance_km real,
    pagination boolean DEFAULT false,
    deduplicate boolean DEFAULT true,
    deduplicate_field text DEFAULT ''::text,
    started_at text DEFAULT ''::text,
    results_on_disk boolean DEFAULT false,
    results_file_path text DEFAULT ''::text,
    updated_at text DEFAULT ''::text,
    deleted_at text
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.recycle_bin OWNER TO dataforge';
   END IF;
END $$;
-- Name: schema_version; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.schema_version (
    version integer NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.schema_version OWNER TO dataforge';
   END IF;
END $$;
-- Name: worker_heartbeats; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.worker_heartbeats (
    worker_id text NOT NULL,
    last_heartbeat text NOT NULL,
    hostname text DEFAULT ''::text NOT NULL,
    pid integer DEFAULT 0 NOT NULL,
    started_at text DEFAULT ''::text NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.worker_heartbeats OWNER TO dataforge';
   END IF;
END $$;
-- Name: world_state; Type: TABLE; Schema: public; Owner: dataforge
CREATE TABLE IF NOT EXISTS public.world_state (
    id text NOT NULL,
    payload text NOT NULL,
    updated_at text NOT NULL
);


DO $$
BEGIN
   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataforge') THEN
      EXECUTE 'ALTER TABLE public.world_state OWNER TO dataforge';
   END IF;
END $$;
-- Name: job_events event_id; Type: DEFAULT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.job_events ALTER COLUMN event_id SET DEFAULT nextval('public.job_events_event_id_seq'::regclass);
-- Name: idempotency_keys idempotency_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (idem_key);
-- Name: job_events job_events_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_pkey PRIMARY KEY (event_id);
-- Name: job_results job_results_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.job_results
    ADD CONSTRAINT job_results_pkey PRIMARY KEY (job_id, result_index);
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);
-- Name: queue_schema_version queue_schema_version_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.queue_schema_version
    ADD CONSTRAINT queue_schema_version_pkey PRIMARY KEY (id);
-- Name: queue_task_history queue_task_history_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.queue_task_history
    ADD CONSTRAINT queue_task_history_pkey PRIMARY KEY (id);
-- Name: queue_tasks queue_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.queue_tasks
    ADD CONSTRAINT queue_tasks_pkey PRIMARY KEY (id);
-- Name: recycle_bin recycle_bin_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.recycle_bin
    ADD CONSTRAINT recycle_bin_pkey PRIMARY KEY (id);
-- Name: schema_version schema_version_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.schema_version
    ADD CONSTRAINT schema_version_pkey PRIMARY KEY (version);
-- Name: worker_heartbeats worker_heartbeats_pkey1; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.worker_heartbeats
    ADD CONSTRAINT worker_heartbeats_pkey1 PRIMARY KEY (worker_id, pid);
-- Name: world_state world_state_pkey; Type: CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.world_state
    ADD CONSTRAINT world_state_pkey PRIMARY KEY (id);
-- Name: idx_idempotency_keys_created_at; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at ON public.idempotency_keys USING btree (created_at);
-- Name: idx_job_events_job_id; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON public.job_events USING btree (job_id, event_id);
-- Name: idx_job_results_job_id; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_job_results_job_id ON public.job_results USING btree (job_id);
-- Name: idx_jobs_created_at; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON public.jobs USING btree (created_at DESC);
-- Name: idx_jobs_created_by; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON public.jobs USING btree (created_by);
-- Name: idx_jobs_org_id; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_jobs_org_id ON public.jobs USING btree (org_id);
-- Name: idx_jobs_project_id; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON public.jobs USING btree (project_id);
-- Name: idx_jobs_status; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_jobs_status ON public.jobs USING btree (status);
-- Name: idx_queue_task_history_finished; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_queue_task_history_finished ON public.queue_task_history USING btree (finished_at DESC);
-- Name: idx_queue_task_history_type; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_queue_task_history_type ON public.queue_task_history USING btree (type);
-- Name: idx_queue_tasks_scheduled; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_queue_tasks_scheduled ON public.queue_tasks USING btree (scheduled_at);
-- Name: idx_queue_tasks_status_priority; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_priority ON public.queue_tasks USING btree (status, priority);
-- Name: idx_rate_limits_key_ts; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_rate_limits_key_ts ON public.rate_limits USING btree (key, "timestamp");
-- Name: idx_recycle_bin_created_at; Type: INDEX; Schema: public; Owner: dataforge
CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON public.recycle_bin USING btree (created_at DESC);
-- F-DB-003: tenant indexes for ``recycle_bin`` so org/project-scoped
-- admin queries don't fall back to a full table scan as the recycle
-- volume grows.
CREATE INDEX IF NOT EXISTS idx_recycle_bin_org_id ON public.recycle_bin USING btree (org_id);
CREATE INDEX IF NOT EXISTS idx_recycle_bin_project_id ON public.recycle_bin USING btree (project_id);
-- Name: job_events job_events_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.job_events
    ADD CONSTRAINT job_events_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;
-- Name: job_results job_results_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dataforge
ALTER TABLE ONLY public.job_results
    ADD CONSTRAINT job_results_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;

-- =============================================================================
-- Schema version stamp — INSERT idempotent guard.
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.schema_version (
    version integer PRIMARY KEY,
    applied_at timestamp without time zone DEFAULT now() NOT NULL,
    comment text
);
INSERT INTO public.schema_version (version, comment)
VALUES (8, '008_postgres_storage_v8 idempotent')
ON CONFLICT (version) DO NOTHING;

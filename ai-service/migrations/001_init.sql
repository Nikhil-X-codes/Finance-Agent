BEGIN;
CREATE SCHEMA IF NOT EXISTS finance_agent;
REVOKE ALL ON SCHEMA finance_agent FROM PUBLIC;
DO $$
DECLARE role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA finance_agent FROM %I', role_name);
    END IF;
  END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS finance_agent.users (
  id text PRIMARY KEY,
  email text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS finance_agent.portfolio_snapshots (
  id text PRIMARY KEY,
  user_id text REFERENCES finance_agent.users(id),
  holdings_json jsonb NOT NULL,
  source text DEFAULT 'STATEMENT',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS finance_agent.trade_log (
  id text PRIMARY KEY,
  user_id text REFERENCES finance_agent.users(id),
  ticker text NOT NULL,
  transaction_type text CHECK (transaction_type IN ('BUY', 'SELL')),
  quantity double precision NOT NULL,
  price double precision NOT NULL,
  trade_date date NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS finance_agent.reports (
  id text PRIMARY KEY,
  user_id text REFERENCES finance_agent.users(id),
  snapshot_id text REFERENCES finance_agent.portfolio_snapshots(id),
  report_json jsonb NOT NULL,
  generated_via text DEFAULT 'LLM',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS finance_agent.api_cache (
  cache_key text PRIMARY KEY,
  response_json jsonb NOT NULL,
  cached_at bigint NOT NULL,
  expires_at bigint NOT NULL,
  source text
);
CREATE INDEX IF NOT EXISTS snapshots_user_created_idx ON finance_agent.portfolio_snapshots (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS trades_user_date_idx ON finance_agent.trade_log (user_id, trade_date, created_at);
CREATE INDEX IF NOT EXISTS reports_user_created_idx ON finance_agent.reports (user_id, created_at DESC);
COMMIT;

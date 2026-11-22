BEGIN;
ALTER TABLE finance_agent.portfolio_snapshots
  ADD COLUMN IF NOT EXISTS coverage_start date,
  ADD COLUMN IF NOT EXISTS coverage_end date,
  ADD COLUMN IF NOT EXISTS statement_key text,
  ADD COLUMN IF NOT EXISTS import_metadata jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS snapshots_user_statement_idx
  ON finance_agent.portfolio_snapshots (user_id, statement_key);
CREATE TABLE IF NOT EXISTS finance_agent.statement_previews (
  id text PRIMARY KEY,
  user_id text NOT NULL REFERENCES finance_agent.users(id),
  statement_key text NOT NULL,
  parsed_json jsonb NOT NULL,
  snapshot_id text REFERENCES finance_agent.portfolio_snapshots(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS previews_user_created_idx ON finance_agent.statement_previews (user_id, created_at);
COMMIT;

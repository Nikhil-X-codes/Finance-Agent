# Finance Agent

Finance Agent imports Indian broker statements, tracks trades, generates portfolio reports, answers portfolio questions, and provides stock and mutual fund research.

Next.js owns sessions and application data. FastAPI handles statement parsing, market research, and LangGraph workflows. Both services use Supabase Postgres. See [AGENTS.md](AGENTS.md) for the phased architecture plan.

## Local setup

Use Node.js 22 or newer and Python 3.11 or newer. Install the AI service dependencies from the repository root.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ai-service/requirements.txt
```

Install the frontend dependencies from its own directory.

```powershell
Set-Location frontend
npm ci
```

Create a Supabase staging project. Apply [001_init.sql](ai-service/migrations/001_init.sql) and [002_statement_imports.sql](ai-service/migrations/002_statement_imports.sql), in that order, through the SQL Editor or `psql` with `ON_ERROR_STOP=1`. The migration creates the private `finance_agent` schema. Keep it out of the Data API's exposed schemas.

Use the same Postgres database in both environments. On an IPv4 network, choose **Session pooler** in Supabase Connect. Download the Supabase CA from Database Settings and save it locally, for example under `ai-service/.certs/`. Use `sslmode=verify-full` and set `sslrootcert` to the URL-encoded absolute certificate path in both connection strings. Use the database owner for migrations. Keep connection strings out of browser code and version control. [Supabase connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres) · [Supabase TLS settings](https://supabase.com/docs/guides/platform/ssl-enforcement)

`frontend/.env.local`

```dotenv
SUPABASE_DB_URL=<Postgres connection string>
FASTAPI_URL=http://localhost:8000
INTERNAL_API_KEY=<shared random secret>
SESSION_PASSWORD=<random 64-character hexadecimal secret>
```

`ai-service/.env`

```dotenv
SUPABASE_DB_URL=<Postgres connection string>
INTERNAL_API_KEY=<same shared random secret>
GROQ_API_KEY=<Groq key>
```

Groq powers statement extraction, Q&A, and advisory explanations. `NEWSAPI_KEY` configures the optional NewsAPI source. Serve production deployments over HTTPS so the secure session cookie can be sent. Changing the session password invalidates existing cookies.

Generate a session secret with the command below, set it in `frontend/.env.local`, and restart Next.js. Hexadecimal output avoids Next.js expanding dollar signs in the value. If a PowerShell environment variable named `SESSION_PASSWORD` is set, it takes precedence over the file.

```powershell
node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))"
```

Run FastAPI from the repository root in one terminal.

```powershell
Set-Location ai-service
..\.venv\Scripts\python.exe -m uvicorn src.api.main:app --loop asyncio:SelectorEventLoop --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal, start Next.js from `frontend`.

```powershell
Set-Location frontend
npm run dev
```

Open the website at `http://localhost:3000`, or use the URL printed by Next.js if it selects a different port. Port 8000 runs FastAPI. Its root page links to the local website, and `http://127.0.0.1:8000/health` checks the service. A browser request to `/docs` returns 403 because API documentation requires the internal service key.

## SQLite migration and rollback

1. Pause writes in the legacy app, make a consistent SQLite backup using SQLite's backup facility, and keep the legacy checkout and configuration. Include WAL contents in the backup by using the backup facility instead of copying only the main database file while it is active.
2. Inspect the backup with a dry run. It validates source data and does not open a Postgres connection.

   ```powershell
   .\.venv\Scripts\python.exe ai-service/scripts/import_sqlite.py --source <backup.db>
   ```

3. Confirm the database in `SUPABASE_DB_URL` before transfer. Rehearse on staging with synthetic data or an authorized backup. Run the import and then verify its contents.

   ```powershell
   .\.venv\Scripts\python.exe ai-service/scripts/import_sqlite.py --source <backup.db> --execute
   .\.venv\Scripts\python.exe ai-service/scripts/import_sqlite.py --source <backup.db> --verify
   ```

   The importer keeps original IDs, hashes, timestamps, and JSON. It verifies the imported rows inside one transaction and rolls back if a conflicting row differs. Retry with the same backup is safe. The provider cache starts fresh.

4. Verify login for an imported account, representative snapshots and reports, and writes after the services restart. Point the deployment at the confirmed production database only after staging checks pass. Before reopening writes, rollback is the previous deployment with the preserved SQLite backup. If Postgres has accepted writes, pause again and reconcile that data before rollback.

## Portfolio and statement rules

- PDF files need a readable text layer. CSV, XLSX, and XLS readers process complete rows in bounded batches. The preview identifies unrecognized rows and lets the user confirm the statement end date. The first successful confirmation of a given file is reused for that account.
- The latest confirmed statement by coverage date supplies starting inventory. Replay manually entered trades strictly after that date, in trade-date and entry order. The as-of date is inclusive. For imported legacy snapshots without coverage dates, preserve the legacy entry-timestamp cutoff. With no statement, trades establish the positions.
- Holdings use weighted-average acquisition cost. Partial sales realize P&L for the sold quantity, and reopening starts a new cost basis. Fees, tax-lot accounting, and manual trades before the selected statement's coverage are outside this computation. A new statement supplies the baseline realized history available from that statement. Legacy oversells that cannot be replayed are shown as trade-log issues.
- Quotes have their statement source and as-of date. Quoted market value and unrealized P&L remain unavailable when any active holding lacks a quote. A legacy price equal to acquisition cost with unknown provenance is treated as unavailable.
- Dashboard and report risk use the same invested-cost concentration rules. A single holding is medium from 25% and high from 40%. A known sector is medium from 45% and high from 60%. Missing cost makes the calculation unavailable. The trade write endpoint enforces available quantity regardless of the advisory model response.

## Q&A and NSE market data

Reports and Q&A use separate LangGraph workflows and stream completed steps. Next.js saves the finished report in Postgres before forwarding the completion event. Trade review calls a service directly for deterministic checks and optional advice. Q&A classifies the question, selectively retrieves structured account or market records, checks the evidence, and cites it. Pure quote questions render directly from the provider's price and timestamp. Historical quotes require a trading date in `YYYY-MM-DD` format.

For informational, non-commercial use permitted by NSE, set `NSE_MARKET_DATA=true` in `ai-service/.env` and restart FastAPI. Stocks, public-market Q&A, and report enrichment share the NSE CM Market Live quote adapter. NSE Bhavcopy handles symbol lookup, daily charts, exact-date closes, and corporate actions. Search by NSE ticker for the most reliable matches. The chart shows unadjusted closes and reports a split- and bonus-adjusted price return when the corporate-action data and factors are available. Market timestamps are displayed in IST. [NSE MCP documentation and terms](https://www.nseindia.in/nse-mcp)

The local portfolio project uses the public feed for informational, non-commercial use. A fresh checkout defaults to disabled until configured. Commercial use requires a provider agreement covering quotes, historical prices, and corporate actions. [NSE market data subscriptions](https://www.nseindia.com/static/nse-data-and-analytics/data-information-vending)

Stocks, Q&A, and report enrichment call [MarketDataService](ai-service/src/services/market_data.py), which selects the NSE MCP adapter in informational mode. To add a licensed feed, implement `MarketDataProvider` and register it in that service. The contract covers quotes, market-mover rankings, symbol lookup, daily history, and exact-date closes.

Stocks uses the provider’s market-movers ranking and displays each stock’s quote timestamp separately from the ranking. `NSE_QUOTE_MAX_AGE_SECONDS` controls when a quote is labeled recent and defaults to 360. `NSE_MCP_TIMEOUT_SECONDS` sets the per-call MCP timeout and defaults to 15. Stock fundamentals use the requested exchange symbol with Screener. Fund comparisons return matching categories and leave the data date unknown when the provider does not supply a common date.

Funds displays each scheme’s latest NAV and NAV date from FinAPI. Additional return, risk, and expense metrics appear when the provider supplies them. Set `FINAPI_UPVALY_API_KEY` in `ai-service/.env` if your FinAPI account includes access to those fields. [FinAPI plans and data coverage](https://finapi.upvaly.com/)

Market Q&A can answer “What is the latest available price of INFY?” and can look up one closing price using a date in `YYYY-MM-DD` format. Use the Stocks detail page for the one-month daily chart. Multi-session history, moving-average comparisons, and corporate-action lists are unavailable as chat answers.

## Verification

Run frontend unit tests with `node --test frontend/tests/api.test.mjs frontend/tests/portfolio.test.mjs`.

Set `SUPABASE_TEST_DB_URL` to a **disposable, migrated database** before running the frontend smoke test. It creates synthetic users and trades. FastAPI is stubbed for this test.

```powershell
node frontend/tests/smoke.mjs
```

Install the optional backend test dependencies and run the checks from the repository root. With `SUPABASE_TEST_DB_URL` set, the suite also exercises report streaming and real Postgres cache operations across an application restart.

```powershell
.\.venv\Scripts\python.exe -m pip install -r ai-service/requirements-dev.txt
Set-Location ai-service
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run deterministic Q&A fixtures from `ai-service` using `..\.venv\Scripts\python.exe -m evals.run`. The fixtures exercise the production graph with synthetic portfolios and quotes. GitHub Actions runs these checks without provider keys.

For model-judged scores, install `requirements-eval.txt`, set `EVAL_API_KEY` and `EVAL_MODEL`, and run:

```powershell
..\.venv\Scripts\python.exe -m evals.run --live-answer --judge --thresholds evals/thresholds-v1.json --output ragas-report.json
```

`GROQ_API_KEY` configures the live answer model. Set `EVAL_BASE_URL` if the evaluation model uses an OpenAI-compatible provider. The report includes per-case checks and Ragas averages grouped by intent. The versioned thresholds gate faithfulness, context precision, and context recall. Factual correctness is reported separately for review. The `QA evaluations` workflow supports a manual Ragas run with the same thresholds. Use `--case CASE_ID` to retry a case and `--judge-timeout SECONDS` to adjust the per-case scoring limit for a slow judge.

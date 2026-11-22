# Finance Agent architecture migration

Use this plan for architecture and feature changes in this repository. Complete the exit checks for each phase before retiring the code it replaces. Keep phases independently reviewable and record the checks that ran, the external dependencies that blocked verification, and any intentional behavior changes.

## Baseline

Before the migration, Next.js used SQLite for app data, FastAPI used SQLite for cache and graph checkpoints, and four routes calculated portfolio holdings separately. Both services now use Postgres and shared portfolio facts. LangGraph handles Q&A and reports. Trade review runs as a direct service call. The repository includes offline evaluations and an optional NSE market feed.

## Target architecture

```text
Browser
  -> Next.js server routes and authenticated session
      -> Supabase Postgres for accounts, snapshots, trades, and saved reports
      -> FastAPI for statement parsing, portfolio analysis, and market data
          -> LangGraph for Q&A and advisory reports
          -> Supabase Postgres for provider cache
          -> Market-data adapters and model providers

Offline Ragas suite -> same Q&A graph with synthetic cases and reference answers
```

- Derive the user identity from the authenticated session. Keep database credentials, service keys, and model credentials server-side. Preserve existing account IDs and password hashes during the database migration. A move to Supabase Auth is a separate decision.
- Give portfolio accounting a single owner. The dashboard, trade validation, reports, and Q&A must use the same portfolio facts and data timestamps.
- Keep arithmetic, permissions, holdings checks, and persistence in application code. Use the model for intent classification when rules are inconclusive and for explanations grounded in supplied evidence.
- Keep reports, Q&A, and statement import as explicit workflows with typed inputs and outputs. Use LangGraph for orchestration where branching, progress, or resumability adds value.

## Phase 1 — Establish the baseline and secure the API boundary

- Identify active browser callers, API contracts, database files, and environment variables. Add smoke coverage for sign-in, statement preview and confirmation, trade entry, reports, Q&A, stocks, and funds.
- Route browser requests for private operations through authenticated Next.js endpoints. Tighten the FastAPI service boundary, remove browser-facing internal keys and the production session-secret fallback, and derive user identity on the server. Scope data access to the authenticated owner.
- Isolate the existing Q&A retriever per request immediately. Keep user portfolios out of shared caches and avoid sending private holdings or full prompts to tracing or eval services by default.
- Replace the placeholder run instructions with the actual app entry points and document provider configuration.

**Exit checks** — An unauthenticated browser cannot access private flows. Two overlapping Q&A requests cannot retrieve each other’s data. Existing entry points still work.

**Verification status** — The frontend API smoke test passes in development and production builds against local Postgres with a stub upstream service. The Python middleware and concurrent retrieval tests pass.

**Local browser entry** — FastAPI exposes a small help page that links to the Next.js website. API docs and private endpoints require the service key. Sign-in and registration share one form, and sign-out uses an HTTP 303 redirect so the browser loads sign-in with GET. Verified the API boundary in Python and the production build, registration, invalid credentials, sign-in, and sign-out in Chrome at a phone viewport using local Postgres.

**Dashboard styling** — Tailwind resolves its config and source paths explicitly. Next.js uses separate development and production output directories. The API smoke test checks that the browser receives Tailwind layout rules. Chrome verified the portfolio sidebar at 1280 px, wrapped navigation at 390 px, and the statement import link at both sizes.

**Frontend setup** — Install and start Next.js from `frontend/`. That directory owns the npm manifest and lockfile.

## Phase 2 — Move persistence to Supabase Postgres

- Add versioned migrations for application data and service-owned tables. Protect application tables with explicit role grants and row-level security for exposed tables. Keep the provider cache private and manage its Postgres pool through the FastAPI lifecycle.
- Write a repeatable SQLite import with a read-only source and a dry-run or verification mode. Preserve app IDs, password hashes, ownership, dates, holdings, and report JSON. Compare table counts and representative records, verify referential integrity, and test sign-in with an imported account. Start with an empty provider cache.
- Convert database callers to async and verify that streamed report completion follows successful persistence. Remove SQLite runtime dependencies, auto-created production databases, and the report parser’s second trade lookup after cutover. Keep backup and rollback instructions. Use a staging project and confirm the migration target before transferring existing user data.

**Exit checks** — A fresh install and a rehearsal against an existing database both pass. Writes survive restarts. Users can access only their own data. All normal runtime paths use Supabase Postgres.

**Verification status** — Applied both migrations to local Postgres and hosted Supabase. Verified the SQLite import against the hosted target. Next.js verified the Session pooler hostname and CA over TLS. Local tests also verified imported sign-in and persistence across a Postgres restart.

## Phase 3 — Make portfolio accounting and statement imports consistent

- Validate parsed PDF and spreadsheet rows before showing the preview. Preserve statement coverage dates, recognized and unrecognized rows, ticker or ISIN, and any imported realized trades. Make confirmation safe to retry. Verify each advertised file format using fixtures.
- Implement one portfolio calculation used by all callers. Document how trades are matched to statement coverage, how backdated trades are handled, and which cost-basis rules the app uses. Account for partial sales, repeated imports, sold and reopened positions, and concurrent writes. Preserve and handle legacy snapshots with missing metadata.
- Distinguish invested cost, quoted market value, realized P&L, and unrealized P&L. Preserve price source and timestamp and represent missing prices explicitly.
- Enforce trade invariants at the write boundary. Keep AI trade explanations advisory and return an explicit unavailable status when analysis fails. Use one documented risk calculation for dashboard and report inputs.

**Exit checks** — A shared fixture yields matching facts across dashboard, report, Q&A, and validation. Invalid sales fail at the write boundary. Tests cover partial sales, backdated entries, concurrent sells, repeat imports, and missing prices.

**Verification status** — The API smoke and regression suites cover the replay, ownership, and statement retry rules. PDF, CSV, XLSX, and XLS reading passed synthetic fixtures. Groq extracted a synthetic statement with the expected coverage date and missing price.

## Phase 4 — Rebuild LangGraph routing and Q&A grounding

```text
FastAPI -> workflow by authenticated route
  REPORT -> normalize holdings -> enrich -> summarize facts -> compute risk -> explain -> format -> END
  QA -> parse question -> route by intent
      PORTFOLIO -> fetch authorized facts -> check evidence -> answer or clarify
      FINANCE   -> education or public market data -> answer or clarify
  TRADE_VALIDATE (direct service) -> deterministic checks -> optional explanation
```

- Give question parsing a typed result with primary intent, referenced symbols or dates where applicable, and an ambiguity outcome. Use explicit private-portfolio cues first. Use structured model output for ambiguous wording and recent turns only to resolve references. A held ticker alone does not make a public market question private.
- Route personal holdings, trades, allocation, and P&L questions to the authenticated portfolio facts. Route educational or public market questions to the finance path. For a mixed question, collect both evidence types without sending account records to a market provider. Ask for clarification when the meaning remains ambiguous, and say when a portfolio, date, or reliable source is unavailable.
- Use **selective, Self-RAG-inspired retrieval** for changing account and public facts. Retrieve typed records with exact ticker or date matches where possible and check evidence before generating. Keep retrieval state scoped to the request. The older embedding path was retired because it recalculated portfolio facts. Evaluate text retrieval or CAG later for a stable, versioned educational corpus if it improves cost or latency.
- Replace the old classification hidden inside the answer generator, global portfolio vector index, stale graph aliases, and duplicate UI/API paths. Use typed graph state, explicit errors, and real progress events. Keep a report checkpoint if an actual pause, resume, or recovery requirement exists. Keep statement confirmation tied to the import workflow.

**Exit checks** — Fixtures cover portfolio-only, general finance, public quote for a held symbol, mixed, follow-up, ambiguous, and empty-portfolio questions. Route and evidence assertions pass. Missing facts produce an explicit limitation and citations resolve to the evidence used.

**Architecture cleanup** — Removed the single-node trade graph, legacy embedding retrieval, and report checkpoint writes. Report generation has one forward flow and the completed report is stored by Next.js. Legacy checkpoint tables are outside the runtime path. Reports and Q&A use the same portfolio-summary helper. Dated public quotes appear separately from statement-based accounting in reports.

**Verification status** — All 21 Python tests passed against disposable Postgres, including report streaming and cache persistence across a restart. All 12 deterministic Q&A cases, eight frontend tests, and the frontend API smoke test passed.

## Phase 5 — Add Ragas and regression gates

- Build a versioned synthetic dataset while implementing Phase 4. Include known holdings and prices, missing data, multi-turn intent changes, conflicting facts, and cases where retrieval should be skipped. Record reference answers and expected routes.
- Run the same Q&A graph used by the app in an offline evaluation command. Pass the actual evidence supplied to the answer node into Ragas. Score faithfulness, context precision and recall where retrieval is expected, and factual correctness against references. Report results by question type. For answers without retrieval, score applicable answer metrics and assert the route independently.
- Add deterministic assertions for amounts, quantities, routing, citation provenance, user isolation, and empty evidence. Mock providers for fast CI checks. Keep model-judged evals as a separate job using configurable evaluator credentials and versioned thresholds after recording the baseline. Keep real account data out of fixtures and evaluator payloads.

**Exit checks** — The evaluator reads fixture cases, runs the graph, prints per-case and aggregate results, and returns a failing exit status when configured gates fail. CI can run the deterministic checks without provider credentials.

**Verification status** — All 12 versioned cases pass deterministic routing and evidence checks. Combining successful live results across runs passed the three retrieval thresholds, with eight factual-correctness scores averaging 0.77. The missing-price case passed all four metrics. The full live command still exited with a failure after judge timeouts. A retry scored the mixed-price case, while the latest intent-switch retry hit the judge provider’s rate limit. The combined results use the successful earlier score for that case. Live CI continues to fail when judge errors leave a case unscored.

## Phase 6 — Integrate NSE data and retire superseded code

- Prototype the Stocks page with **NSE CM Market Live** for timestamped quotes and **NSE Bhavcopy** for daily OHLCV. Add provider adapters inside FastAPI so stock pages and LangGraph enrichment can reuse the same normalized data. Keep fundamentals, news, and fund NAV on sources that supply those fields.
- Handle last trading sessions, stale or missing quotes, unavailable providers, and split or bonus adjustments in historical returns. Verify provider coverage against representative symbols, including symbols from imported statements. Confirm permitted use before any public or commercial deployment. NSE limits the public MCP endpoints to informational, non-commercial use. [Official NSE MCP documentation](https://www.nseindia.in/nse-mcp)
- Remove superseded quote and history adapters for supported use cases after parity checks. Remove stale endpoints, configuration, docs, and dependencies as their callers are migrated. Run end-to-end smoke tests and record any intentionally removed user-facing features in the migration notes.

**Exit checks** — The app displays data provenance and market timestamps. Unsupported symbols and stale data have explicit outcomes. The selected feed covers the deployment’s permitted use, and the final smoke tests pass.

**Verification status** — Live quotes were checked for TCS, RELIANCE, INFY, and TATACOMM. Bhavcopy returned 21 daily sessions for TCS, and the adapter rejected a holiday as an exact closing date. The TATASTEEL historical split used the factor published by NSE. A transient corporate-actions outage produced an unavailable adjusted return. Stock search and popular quotes expose the provider, market timestamp, and quote status. The production API smoke test passed using local Postgres. Chrome at a phone viewport verified navigation, missing portfolio prices, Q&A retry and citations, and quote provenance.

**Portfolio project** — The intended use is a non-commercial resume and portfolio project. The local configuration enables the public NSE feed. The default for a fresh checkout is disabled. A commercial deployment would need a licensed feed. [NSE market data subscriptions](https://www.nseindia.com/static/nse-data-and-analytics/data-information-vending)

**Retired code** — Removed the internal `/v1/enrich` endpoint, the placeholder local model download script, and the Yahoo quote and symbol-search adapters. Stocks, Q&A, and report enrichment route current quotes through NSE CM Market Live. Bhavcopy supplies symbol lookup, daily history, and corporate actions.

**Cutover checks** — From the application adapters, verified an `INFY` quote, ticker lookup, 21 Bhavcopy sessions, and an exact-date Q&A close. A direct Bhavcopy request returned HTTP 502 during the first attempt and succeeded on retry. Regression tests confirmed that disabled mode calls neither server and that symbol search uses the CM quote alongside the Bhavcopy match. The frontend build and all 12 deterministic Q&A cases passed.

**Provider interface** — Stocks, current and historical Q&A quotes, and report enrichment use `MarketDataService`. The service selects the NSE MCP provider for permitted informational use. A licensed provider must implement the same quote, market-mover ranking, search, history, and exact-close contract. Requests for multi-session history, moving averages, and corporate-action lists in Q&A produce an explicit unavailable answer.

**Market data values** — Stocks reads the gainers and losers ranking from the provider and gets a timestamped quote for each ranked stock. The fixed stock list and the Screener company alias map were removed. Quote freshness uses the provider’s trade timestamp and a configurable maximum age. Fund comparisons no longer substitute other categories or use the server date as market-data provenance.

**Market movers verification** — The direct adapter returned two live-feed gainers, two losers, and a timestamped quote for a ranked stock. The first direct request timed out during MCP validation and passed after the timeout was made configurable. The focused regression suite and production frontend build passed.

**Portfolio demo fixes** — Qualified the trade-list date in Postgres and verified ordered, owner-scoped history in the production API smoke test. FinAPI’s current category label and per-scheme NAV dates are used in fund comparisons. Live checks against the local backend returned ten stock movers, a timestamped INFY quote, and twelve schemes each for Large Cap and Sectoral/Thematic. The local Next.js health proxy and favicon returned HTTP 200.

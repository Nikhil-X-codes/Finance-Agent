"""Dry-run, import, or verify Finance Agent's legacy SQLite application data."""

import argparse
from contextlib import closing
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

TABLES = {
    "users": ("id", "email", "password_hash", "created_at"),
    "portfolio_snapshots": ("id", "user_id", "holdings_json", "source", "created_at"),
    "trade_log": ("id", "user_id", "ticker", "transaction_type", "quantity", "price", "trade_date", "created_at"),
    "reports": ("id", "user_id", "snapshot_id", "report_json", "generated_via", "created_at"),
}
JSON_COLUMNS = {"holdings_json", "report_json"}


def read_source(path: Path) -> dict[str, list[dict]]:
    uri = path.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite contains broken foreign-key references.")
        rows = {}
        for table, columns in TABLES.items():
            rows[table] = []
            for source in db.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY id"):
                row = dict(source)
                for name in JSON_COLUMNS.intersection(row):
                    row[name] = json.loads(row[name], parse_constant=reject_json_constant)
                stamp = datetime.fromisoformat(row["created_at"])
                row["created_at"] = stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
                if "trade_date" in row:
                    row["trade_date"] = date.fromisoformat(row["trade_date"])
                rows[table].append(row)
        return rows


def reject_json_constant(_):
    raise ValueError("SQLite contains non-finite values in JSON.")


def transfer(rows: dict[str, list[dict]], url: str, verify_only: bool) -> None:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    with psycopg.connect(url, row_factory=dict_row) as conn:
        if not verify_only:
            conn.execute("SELECT pg_advisory_xact_lock(19200816)")
        for table, columns in TABLES.items():
            batch = rows[table]
            if not verify_only and batch:
                placeholders = ", ".join(["%s"] * len(columns))
                values = [
                    tuple(Jsonb(row[k]) if k in JSON_COLUMNS else row[k] for k in columns)
                    for row in batch
                ]
                with conn.cursor() as cursor:
                    cursor.executemany(
                        f"INSERT INTO finance_agent.{table} ({', '.join(columns)}) "
                        f"VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING",
                        values,
                    )
            for offset in range(0, len(batch), 500):
                expected = {row["id"]: row for row in batch[offset:offset + 500]}
                actual = conn.execute(
                    f"SELECT {', '.join(columns)} FROM finance_agent.{table} WHERE id = ANY(%s)",
                    (list(expected),),
                ).fetchall()
                if {row["id"]: row for row in actual} != expected:
                    raise ValueError(f"Verification failed for {table}. The destination has mismatched or missing source rows.")
            print(f"{table}: verified {len(batch)} source rows")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Path to a consistent SQLite backup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Import to the database in SUPABASE_DB_URL")
    mode.add_argument("--verify", action="store_true", help="Compare the target with the read-only SQLite source")
    options = parser.parse_args()
    try:
        rows = read_source(options.source)
        if options.execute or options.verify:
            url = os.environ.get("SUPABASE_DB_URL")
            if not url:
                parser.error("SUPABASE_DB_URL is required for import or target verification")
            transfer(rows, url, verify_only=options.verify)
            print("Import committed." if options.execute else "Read-only target verification complete.")
        else:
            for table, records in rows.items():
                print(f"{table}: validated {len(records)} rows")
            print("Dry run complete. No Postgres connection was opened.")
    except Exception as exc:
        if isinstance(exc, ValueError):
            message = exc.args[0] if str(exc).startswith(("Verification failed", "SQLite contains")) else "Invalid legacy date or JSON."
        else:
            message = f"{type(exc).__name__}. Check the source database and target configuration."
        parser.exit(1, f"Migration failed: {message}\n")


if __name__ == "__main__":
    main()

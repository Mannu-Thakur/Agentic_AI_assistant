"""
migrate_sqlite_to_pg.py — Robust SQLite -> PostgreSQL Migration
"""
import sqlite3
import json
from datetime import datetime
from sqlalchemy import create_engine, MetaData, Table, Boolean, DateTime, JSON, text

SQLITE_PATH = "backend/sql_app.db"
PG_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_assistant"

def parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        try:
            return datetime.strptime(str(val).split(".")[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

def parse_json(val):
    if val is None or val in ('null', '"null"', ''):
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        curr = val
        for _ in range(3):
            if isinstance(curr, str):
                try:
                    curr = json.loads(curr)
                except Exception:
                    break
            else:
                break
        if curr in ('null', '"null"', '', None):
            return None
        return curr
    return None

def migrate():
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    pg_engine = create_engine(PG_URL)
    metadata = MetaData()
    metadata.reflect(bind=pg_engine)

    tables = [
        "users",
        "user_preferences",
        "chats",
        "messages",
        "documents",
        "memories",
        "shared_links",
        "audit_logs",
        "api_keys",
        "remote_mcp_servers"
    ]

    with pg_engine.begin() as pg_conn:
        for table_name in reversed(tables):
            try:
                pg_conn.execute(text(f'TRUNCATE TABLE "{table_name}" CASCADE;'))
            except Exception as e:
                print(f"Could not truncate {table_name}: {e}")

        for table_name in tables:
            if table_name not in metadata.tables:
                print(f"Skipping {table_name} (not in PG metadata)")
                continue

            pg_table = metadata.tables[table_name]
            bool_cols = {col.name for col in pg_table.columns if isinstance(col.type, Boolean)}
            dt_cols = {col.name for col in pg_table.columns if isinstance(col.type, DateTime)}
            json_cols = {col.name for col in pg_table.columns if isinstance(col.type, JSON)}

            rows = sqlite_cur.execute(f'SELECT * FROM "{table_name}"').fetchall()
            if not rows:
                print(f"No rows in {table_name}")
                continue

            count = 0
            skipped = 0
            for row in rows:
                row_dict = dict(row)
                pg_col_names = {c.name for c in pg_table.columns}
                row_dict = {k: v for k, v in row_dict.items() if k in pg_col_names}

                for b_col in bool_cols:
                    if b_col in row_dict and row_dict[b_col] is not None:
                        row_dict[b_col] = bool(row_dict[b_col])
                
                for d_col in dt_cols:
                    if d_col in row_dict and row_dict[d_col] is not None:
                        row_dict[d_col] = parse_dt(row_dict[d_col])

                for j_col in json_cols:
                    if j_col in row_dict:
                        row_dict[j_col] = parse_json(row_dict[j_col])

                stmt = pg_table.insert().values(**row_dict)
                try:
                    with pg_conn.begin_nested():
                        pg_conn.execute(stmt)
                    count += 1
                except Exception:
                    skipped += 1

            print(f"Migrated {count} rows into {table_name} (skipped {skipped} orphan/invalid rows)")

    print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()

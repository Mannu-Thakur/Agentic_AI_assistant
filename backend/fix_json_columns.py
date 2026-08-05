"""
fix_json_columns.py — Convert stringified JSON in PostgreSQL into native JSON objects.
"""
import json
from sqlalchemy import create_engine, text

PG_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_assistant"

def fix_json():
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, tool_calls, developer_metrics, images FROM messages")).fetchall()
        updated = 0
        for r in rows:
            msg_id, tc, dm, img = r[0], r[1], r[2], r[3]
            new_tc = tc
            new_dm = dm
            new_img = img
            changed = False

            if isinstance(tc, str):
                try:
                    new_tc = json.loads(tc)
                    changed = True
                except Exception:
                    new_tc = None
                    changed = True

            if isinstance(dm, str):
                try:
                    new_dm = json.loads(dm)
                    changed = True
                except Exception:
                    new_dm = None
                    changed = True

            if isinstance(img, str):
                try:
                    new_img = json.loads(img)
                    changed = True
                except Exception:
                    new_img = None
                    changed = True

            if changed:
                conn.execute(
                    text("UPDATE messages SET tool_calls = :tc, developer_metrics = :dm, images = :img WHERE id = :id"),
                    {
                        "tc": json.dumps(new_tc) if new_tc is not None else None,
                        "dm": json.dumps(new_dm) if new_dm is not None else None,
                        "img": json.dumps(new_img) if new_img is not None else None,
                        "id": msg_id
                    }
                )
                updated += 1
        print(f"Updated {updated} messages to native JSON objects.")

if __name__ == "__main__":
    fix_json()

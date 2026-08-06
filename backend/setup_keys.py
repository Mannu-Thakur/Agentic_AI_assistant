import sqlite3
import uuid

conn = sqlite3.connect('sql_app.db')
cursor = conn.cursor()

target_user_id = 'df9824c6-a470-437e-9ec0-73bf19c2942c'
source_user_id = 'f365dd04-6dc2-44f9-b5ae-03d4aed1e58c'

rows = cursor.execute(
    "SELECT provider_name, encrypted_api_key, status, available_models FROM api_keys WHERE user_id = ?",
    (source_user_id,)
).fetchall()

for r in rows:
    cursor.execute(
        "INSERT INTO api_keys (id, user_id, provider_name, encrypted_api_key, status, available_models, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (str(uuid.uuid4()), target_user_id, r[0], r[1], r[2], r[3])
    )

conn.commit()
print(f"Successfully copied {len(rows)} verified API keys to user {target_user_id}")

"""
sanitize_messages.py — Clean up string literals in JSON columns.
"""
from sqlalchemy import create_engine, text

PG_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/ai_assistant"

def sanitize():
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text("UPDATE messages SET tool_calls = NULL WHERE tool_calls::text IN ('null', '\"null\"');"))
        conn.execute(text("UPDATE messages SET developer_metrics = NULL WHERE developer_metrics::text IN ('null', '\"null\"');"))
        conn.execute(text("UPDATE messages SET images = NULL WHERE images::text IN ('null', '\"null\"');"))
        print("Sanitized tool_calls, developer_metrics, and images in messages table.")

if __name__ == "__main__":
    sanitize()

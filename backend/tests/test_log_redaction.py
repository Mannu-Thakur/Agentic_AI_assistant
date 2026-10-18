import json
import logging

from app.main import _JsonFormatter


def test_json_formatter_redacts_http_url_query_strings():
    secret = "do-not-write-this-provider-token"
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname="health.py",
        lineno=42,
        msg="HTTP Request: GET %s \"HTTP/1.1 200 OK\"",
        args=(f"https://serpapi.com/account?api_key={secret}&scope=read",),
        exc_info=None,
    )

    rendered = _JsonFormatter().format(record)
    payload = json.loads(rendered)

    assert secret not in rendered
    assert "api_key=" not in rendered
    assert "https://serpapi.com/account?[query redacted]" in payload["message"]
    assert "HTTP/1.1 200 OK" in payload["message"]

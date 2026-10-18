import tempfile
from pathlib import Path

from app.core.storage_paths import resolve_storage_path


def test_keeps_configured_storage_path_when_writable(tmp_path):
    configured = tmp_path / "vector_db"

    resolved = resolve_storage_path(str(configured), "vector_db")

    assert Path(resolved) == configured.resolve()
    assert configured.is_dir()


def test_unwritable_configured_path_falls_back_to_runtime_temp(tmp_path, monkeypatch):
    temp_root = tmp_path / "runtime-temp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(temp_root))

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("test", encoding="utf-8")
    configured = blocker / "uploads"

    resolved = resolve_storage_path(str(configured), "uploads")

    assert Path(resolved) == temp_root / "agentic-ai-assistant" / "uploads"
    assert Path(resolved).is_dir()

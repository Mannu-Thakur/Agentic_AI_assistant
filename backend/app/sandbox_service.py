"""Minimal, separately deployed Python execution service.

This process is intentionally not mounted into the public application network.
It accepts a deliberately small, computation-only Python subset and executes it
in a disposable low-privilege process.  The Docker deployment supplies the
stronger boundary: no egress, read-only filesystem, dropped Linux capabilities,
PID/memory/CPU limits, and an internal-only network.
"""

from __future__ import annotations

import ast
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Isolated Code Sandbox", docs_url=None, redoc_url=None)

_MAX_CODE_CHARS = 20_000
_MAX_OUTPUT_BYTES = 65_536
_MAX_AST_NODES = 10_000
_SAFE_CALLS = {
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int",
    "len", "list", "max", "min", "print", "range", "round", "set",
    "sorted", "str", "sum", "tuple", "zip",
}
_ALLOWED_NODES = {
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.Name, ast.Load,
    ast.Store, ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass, ast.List,
    ast.Tuple, ast.Set, ast.Dict, ast.Subscript, ast.Slice, ast.Call, ast.keyword,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
    ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
}


class ExecuteRequest(BaseModel):
    code: str = Field(min_length=1, max_length=_MAX_CODE_CHARS)


class ExecuteResponse(BaseModel):
    output: str
    exit_code: int
    timed_out: bool = False


def _validate_code(code: str) -> None:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise HTTPException(status_code=422, detail=f"Python syntax error: {exc.msg}") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        raise HTTPException(status_code=422, detail="Program is too complex for the sandbox.")
    for node in nodes:
        if type(node) not in _ALLOWED_NODES:
            raise HTTPException(
                status_code=422,
                detail=f"Sandbox policy blocks {type(node).__name__}. Imports, attributes, files, and network access are not available.",
            )
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in {"globals", "locals", "vars", "help", "dir"}):
            raise HTTPException(status_code=422, detail="Sandbox policy blocks reflective Python names.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_CALLS:
                raise HTTPException(status_code=422, detail="Sandbox policy blocks this function call.")


def _limit_resources() -> None:
    """Linux-only last line of defense, applied inside the child process."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_OUTPUT_BYTES, _MAX_OUTPUT_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except Exception:
        # The service is supported only in the hardened Linux container.  The
        # outer Docker limits remain mandatory even if one rlimit is unavailable.
        pass


def _execute(code: str) -> ExecuteResponse:
    _validate_code(code)
    with tempfile.TemporaryDirectory(prefix="safe-python-") as temp_dir:
        root = Path(temp_dir)
        script = root / "program.py"
        stdout_path = root / "stdout.txt"
        stderr_path = root / "stderr.txt"
        script.write_text(code, encoding="utf-8")
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", "-S", str(script)],
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    cwd=temp_dir,
                    env={"PATH": os.environ.get("PATH", "")},
                    timeout=4,
                    check=False,
                    close_fds=True,
                    start_new_session=True,
                    preexec_fn=_limit_resources if os.name == "posix" else None,
                )
            except subprocess.TimeoutExpired:
                return ExecuteResponse(output="Execution timed out after 4 seconds.", exit_code=124, timed_out=True)
        stdout_text = stdout_path.read_bytes()[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace").strip()
        stderr_text = stderr_path.read_bytes()[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            return ExecuteResponse(output=stdout_text or "[Execution completed with no output]", exit_code=0)
        detail = stderr_text or stdout_text or "The sandbox process exited without diagnostic output."
        return ExecuteResponse(output=f"Runtime error (exit {proc.returncode}):\n{detail}", exit_code=proc.returncode)


def _require_token(token: str | None) -> None:
    expected = os.environ.get("SANDBOX_SHARED_SECRET")
    if not expected or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized sandbox request.")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    x_sandbox_token: str | None = Header(default=None),
) -> ExecuteResponse:
    _require_token(x_sandbox_token)
    return _execute(request.code)

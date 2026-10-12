import subprocess
import shutil
import os
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/git", tags=["Git Integration"])


class GitStatusResponse(BaseModel):
    git_installed: bool
    is_repo: bool
    branch: Optional[str] = None
    latest_commit: Optional[str] = None
    remote_url: Optional[str] = None
    modified_files: int = 0
    untracked_files: int = 0
    is_clean: bool = True
    repo_root: Optional[str] = None


class CommitSuggestionResponse(BaseModel):
    success: bool
    suggested_message: str
    changed_files_count: int
    diff_summary: Optional[str] = None


def _run_git_cmd(args: list, cwd: Optional[str] = None) -> tuple[int, str, str]:
    """Execute a git command with timeout safeguards."""
    git_bin = shutil.which("git")
    if not git_bin:
        return 1, "", "Git binary not found on system PATH"
    try:
        proc = subprocess.run(
            [git_bin] + args,
            cwd=cwd or os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Git command timed out"
    except Exception as e:
        return 1, "", str(e)


@router.get("/status", response_model=GitStatusResponse)
async def get_git_status(current_user=Depends(get_current_user)):
    """Inspect local repository git status, current branch, and clean state."""
    git_installed = bool(shutil.which("git"))
    if not git_installed:
        return GitStatusResponse(git_installed=False, is_repo=False)

    # Check if in a repo
    code, repo_root, _ = _run_git_cmd(["rev-parse", "--show-toplevel"])
    if code != 0 or not repo_root:
        return GitStatusResponse(git_installed=True, is_repo=False)

    # Get branch
    _, branch, _ = _run_git_cmd(["branch", "--show-current"])

    # Get latest commit
    _, commit_info, _ = _run_git_cmd(["log", "-1", "--format=%h %s"])

    # Get remote url
    _, remote_url, _ = _run_git_cmd(["config", "--get", "remote.origin.url"])

    # Get status porcelain
    _, status_out, _ = _run_git_cmd(["status", "--porcelain"])

    modified_count = 0
    untracked_count = 0
    if status_out:
        for line in status_out.splitlines():
            line = line.strip()
            if line.startswith("??"):
                untracked_count += 1
            elif line:
                modified_count += 1

    return GitStatusResponse(
        git_installed=True,
        is_repo=True,
        branch=branch or "HEAD (detached)",
        latest_commit=commit_info or None,
        remote_url=remote_url or None,
        modified_files=modified_count,
        untracked_files=untracked_count,
        is_clean=(modified_count == 0 and untracked_count == 0),
        repo_root=repo_root,
    )


@router.post("/commit-suggestion", response_model=CommitSuggestionResponse)
async def suggest_commit_message(current_user=Depends(get_current_user)):
    """Generate an intelligent conventional commit suggestion from staged diffs."""
    git_installed = bool(shutil.which("git"))
    if not git_installed:
        raise HTTPException(status_code=400, detail="Git is not installed on the host.")

    # Try cached (staged) diff first
    code, diff_cached, _ = _run_git_cmd(["diff", "--cached", "--stat"])
    # If no staged changes, check working tree diff
    if not diff_cached:
        _, diff_cached, _ = _run_git_cmd(["diff", "--stat"])

    # Count modified files
    _, status_out, _ = _run_git_cmd(["status", "--porcelain"])
    lines = [l.strip() for l in status_out.splitlines() if l.strip()] if status_out else []
    file_count = len(lines)

    if not lines and not diff_cached:
        return CommitSuggestionResponse(
            success=True,
            suggested_message="chore: update project dependencies and workspace files",
            changed_files_count=0,
            diff_summary="Working tree is clean. No unstaged or staged changes detected.",
        )

    # Categorize changes
    has_frontend = any("frontend" in l for l in lines)
    has_backend = any("backend" in l for l in lines)
    has_docs = any("README" in l or ".md" in l for l in lines)
    has_tests = any("test" in l for l in lines)

    if has_tests and not (has_frontend or has_backend):
        prefix = "test"
    elif has_docs and not (has_frontend or has_backend):
        prefix = "docs"
    elif has_frontend and has_backend:
        prefix = "feat(workspace)"
    elif has_frontend:
        prefix = "feat(ui)"
    elif has_backend:
        prefix = "feat(api)"
    else:
        prefix = "chore"

    summary_msg = f"{prefix}: update {file_count} file(s) across workspace"

    return CommitSuggestionResponse(
        success=True,
        suggested_message=summary_msg,
        changed_files_count=file_count,
        diff_summary=diff_cached[:500] if diff_cached else f"{file_count} modified files",
    )

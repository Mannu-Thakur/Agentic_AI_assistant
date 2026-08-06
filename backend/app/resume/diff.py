"""
app/resume/diff.py — GitHub-style diff engine for resume sections.

Computes word-level diffs between two ResumeData objects.
"""

from __future__ import annotations

import difflib
from typing import List, Optional, Tuple

from app.resume.models import ResumeData
from app.resume.schemas import DiffSection, DiffResponse


def _word_diff(original: str, new: str) -> List[dict]:
    """
    Compute word-level diff between two strings.
    Returns list of chunks: {"type": "added|removed|unchanged", "text": "..."}
    """
    orig_words = original.split()
    new_words = new.split()

    matcher = difflib.SequenceMatcher(None, orig_words, new_words)
    chunks = []

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            chunks.append({"type": "unchanged", "text": " ".join(orig_words[i1:i2])})
        elif op == "insert":
            chunks.append({"type": "added", "text": " ".join(new_words[j1:j2])})
        elif op == "delete":
            chunks.append({"type": "removed", "text": " ".join(orig_words[i1:i2])})
        elif op == "replace":
            chunks.append({"type": "removed", "text": " ".join(orig_words[i1:i2])})
            chunks.append({"type": "added", "text": " ".join(new_words[j1:j2])})

    return chunks


def _classify_diff(original: str, new_text: str) -> Tuple[str, List[dict]]:
    """Classify overall change type and return word chunks."""
    if not original and new_text:
        return "added", [{"type": "added", "text": new_text}]
    if original and not new_text:
        return "removed", [{"type": "removed", "text": original}]
    if original == new_text:
        return "unchanged", [{"type": "unchanged", "text": original}]

    chunks = _word_diff(original, new_text)
    return "modified", chunks


def compute_resume_diff(
    original: ResumeData,
    tailored: ResumeData,
    section: Optional[str] = None,
) -> DiffResponse:
    """
    Compute GitHub-style diff between two ResumeData objects.
    """
    diffs: List[DiffSection] = []
    additions = 0
    removals = 0
    modifications = 0

    def add_diff(sec: str, field: str, orig: str, new: str):
        nonlocal additions, removals, modifications
        diff_type, chunks = _classify_diff(orig, new)
        if diff_type == "unchanged":
            return
        d = DiffSection(
            section=sec,
            field=field,
            diff_type=diff_type,
            original_text=orig,
            new_text=new,
            chunks=chunks,
        )
        diffs.append(d)
        if diff_type == "added":
            additions += 1
        elif diff_type == "removed":
            removals += 1
        elif diff_type == "modified":
            modifications += 1

    # Summary
    if not section or section == "summary":
        add_diff("summary", "text", original.summary, tailored.summary)
        add_diff("headline", "text", original.headline, tailored.headline)

    # Skills
    if not section or section == "skills":
        orig_skills = " | ".join(
            f"{sg.category}: {', '.join(sg.skills)}" for sg in original.skills
        )
        new_skills = " | ".join(
            f"{sg.category}: {', '.join(sg.skills)}" for sg in tailored.skills
        )
        add_diff("skills", "all", orig_skills, new_skills)

    # Experience
    if not section or section == "experience":
        # Match by id or index
        orig_exp_map = {e.id: e for e in original.experience}
        for exp in tailored.experience:
            orig_e = orig_exp_map.get(exp.id)
            if not orig_e:
                # New entry (unlikely in tailoring)
                add_diff("experience", f"{exp.company} - {exp.role}", "", "\n".join(exp.bullets))
                continue
            for i, (ob, nb) in enumerate(zip(orig_e.bullets, exp.bullets)):
                add_diff(f"experience", f"{exp.company} — bullet {i+1}", ob, nb)
            # Extra bullets
            if len(exp.bullets) > len(orig_e.bullets):
                for nb in exp.bullets[len(orig_e.bullets):]:
                    add_diff(f"experience", f"{exp.company} — new bullet", "", nb)

    # Projects
    if not section or section == "projects":
        orig_proj_map = {p.id: p for p in original.projects}
        for proj in tailored.projects:
            orig_p = orig_proj_map.get(proj.id)
            if not orig_p:
                add_diff("projects", proj.name, "", proj.description)
                continue
            add_diff("projects", f"{proj.name} — description", orig_p.description, proj.description)
            for i, (ob, nb) in enumerate(zip(orig_p.bullets, proj.bullets)):
                add_diff("projects", f"{proj.name} — bullet {i+1}", ob, nb)

    total = additions + removals + modifications
    total_fields = len(diffs) + 1
    change_pct = round((total / total_fields) * 100, 1) if total_fields > 0 else 0.0

    return DiffResponse(
        sections=diffs,
        total_additions=additions,
        total_removals=removals,
        total_modifications=modifications,
        change_percentage=change_pct,
    )

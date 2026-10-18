from app.resume.models import ResumeData
from app.resume.renderer import generate_latex


def test_generated_latex_keeps_email_as_a_mailto_link():
    resume = ResumeData(
        personal={"name": "Avery Test", "email": "avery@example.com"}
    )

    latex = generate_latex(resume)

    assert r"\href{mailto:avery@example.com}{avery@example.com}" in latex
    assert "mailto:https://" not in latex


def test_generated_latex_does_not_duplicate_mailto_scheme():
    resume = ResumeData(
        personal={"name": "Avery Test", "email": "mailto:avery@example.com"}
    )

    latex = generate_latex(resume)

    assert r"\href{mailto:avery@example.com}{avery@example.com}" in latex
    assert "mailto:mailto:" not in latex

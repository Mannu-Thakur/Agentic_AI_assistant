from app.resume.latex_parser import parse_latex_to_resume
from app.resume.models import ResumeData, SkillGroup
from app.resume.renderer import generate_latex


def test_latex_round_trip_preserves_email_and_skill_category():
    resume = ResumeData(
        personal={"name": "Avery Test", "email": "avery@example.com"},
        skills=[SkillGroup(category="Technical Skills", skills=["Python", "Playwright"])],
    )

    parsed = parse_latex_to_resume(generate_latex(resume))

    assert parsed.personal.email == "avery@example.com"
    assert len(parsed.skills) == 1
    assert parsed.skills[0].category == "Technical Skills"
    assert parsed.skills[0].skills == ["Python", "Playwright"]


def test_empty_latex_skill_list_does_not_create_phantom_skills():
    resume = ResumeData(
        personal={"name": "Avery Test"},
        skills=[SkillGroup(category="Technical Skills", skills=[])],
    )

    parsed = parse_latex_to_resume(generate_latex(resume))

    assert parsed.skills == []

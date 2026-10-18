from app.agents.document_agent import _requested_slide_count
from app.agents.supervisor import _forced_agent_specs


def test_explicit_mission_routes_downloadable_presentation_to_document_agent():
    query = (
        "Create a downloadable three-slide PowerPoint about CRAG vs Self-RAG. "
        "Slide 1: goals. Slide 2: side-by-side retrieval flow. Slide 3: validation checks."
    )

    assert _forced_agent_specs(query) == [
        {"agent": "document", "query": query, "doc_type": "pptx"}
    ]


def test_explicit_mission_preserves_research_and_artifact_specialists():
    query = "Research current hybrid retrieval practice and create a PowerPoint deck."

    assert [task["agent"] for task in _forced_agent_specs(query)] == [
        "document",
        "web_research",
    ]


def test_step_based_mission_does_not_silently_return_to_ordinary_chat():
    query = (
        "Create a three-step plan to compare CRAG and Self-RAG, explain each, "
        "then provide a comparison and final verification checklist."
    )

    assert [task["agent"] for task in _forced_agent_specs(query)] == ["web_research"]


def test_document_agent_honors_numeric_and_worded_total_slide_counts():
    assert _requested_slide_count("Create a three-slide PowerPoint") == 3
    assert _requested_slide_count("Generate a 7 slide deck") == 7
    assert _requested_slide_count("Create a general presentation") is None

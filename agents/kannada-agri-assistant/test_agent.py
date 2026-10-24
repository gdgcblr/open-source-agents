from agent import app, extract_answer_text


def test_homepage_renders_ui():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'Kannada Agri Assistant' in response.data


def test_extract_answer_text_handles_structured_content():
    content = [{"type": "text", "text": "சிறந்த பதில்"}]
    assert extract_answer_text(content) == "சிறந்த பதில்"

    content = {"type": "text", "text": "வணக்கம்"}
    assert extract_answer_text(content) == "வணக்கம்"


def test_missing_question_returns_400():
    client = app.test_client()
    response = client.get('/ask')
    assert response.status_code == 400
    payload = response.get_json()
    assert "No question provided" in payload["error"]

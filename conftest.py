# conftest.py
import pytest

@pytest.fixture(autouse=True)
def mock_generate_ai_message(monkeypatch):
    def fake_ai_message(*args, **kwargs):
        return "테스트용 AI 메시지입니다."

    monkeypatch.setattr("ai_service.generate_ai_message", fake_ai_message)
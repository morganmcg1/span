"""Tests for voice server FastAPI endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from span.voice.server import _get_user_and_lesson_plan, app


class TestGetUserAndLessonPlan:
    """Tests for _get_user_and_lesson_plan helper function."""

    def test_returns_user_and_plan_when_user_exists(self, memory_db, sample_user):
        """Should return user ID, lesson plan, and is_news_lesson flag when user exists."""
        user_id = memory_db.create_user(sample_user)

        result_id, result_plan, is_news_lesson = _get_user_and_lesson_plan(memory_db)

        assert result_id == user_id
        assert result_plan is not None
        assert isinstance(is_news_lesson, bool)

    def test_returns_default_user_when_no_user(self, memory_db):
        """Should return default user ID, None plan, and is_news_lesson flag when no user."""
        result_id, result_plan, is_news_lesson = _get_user_and_lesson_plan(memory_db)

        # DEFAULT_USER_ID is 1
        assert result_id == 1
        assert result_plan is None
        assert isinstance(is_news_lesson, bool)

    def test_logs_warning_when_no_user(self, memory_db, capsys):
        """Should print warning when falling back to default user."""
        with patch("span.voice.server.console") as mock_console:
            _get_user_and_lesson_plan(memory_db)
            # Check that a warning was printed
            mock_console.print.assert_called()
            call_args = str(mock_console.print.call_args)
            assert "Warning" in call_args or "yellow" in call_args


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, config):
        """Should return status ok."""
        # We need to set global config before testing
        import span.voice.server as server_module

        # Save original values
        orig_config = server_module.config
        orig_db = server_module.db

        try:
            server_module.config = config
            server_module.db = MagicMock()

            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
        finally:
            # Restore original values
            server_module.config = orig_config
            server_module.db = orig_db


class TestDialoutEndpoint:
    """Tests for /dialout endpoint."""

    def test_dialout_returns_error_without_api_key(self):
        """Should return error when DAILY_API_KEY not configured."""
        import span.voice.server as server_module

        # Create config without daily_api_key
        mock_config = MagicMock()
        mock_config.daily_api_key = None

        orig_config = server_module.config
        orig_db = server_module.db

        try:
            server_module.config = mock_config
            server_module.db = MagicMock()

            client = TestClient(app)
            response = client.get("/dialout")

            assert response.status_code == 200
            assert "error" in response.json()
            assert "DAILY_API_KEY" in response.json()["error"]
        finally:
            server_module.config = orig_config
            server_module.db = orig_db

    def test_dialout_returns_error_without_phone_number(self):
        """Should return error when USER_PHONE_NUMBER not configured."""
        import span.voice.server as server_module

        # Create config with API key but no phone
        mock_config = MagicMock()
        mock_config.daily_api_key = "test-key"
        mock_config.user_phone_number = None

        orig_config = server_module.config
        orig_db = server_module.db

        try:
            server_module.config = mock_config
            server_module.db = MagicMock()

            client = TestClient(app)
            response = client.get("/dialout")

            assert response.status_code == 200
            assert "error" in response.json()
            assert "USER_PHONE_NUMBER" in response.json()["error"]
        finally:
            server_module.config = orig_config
            server_module.db = orig_db


class TestWebEndpoint:
    """Tests for /web endpoint."""

    def test_web_returns_error_without_api_key(self):
        """Should return error when DAILY_API_KEY not configured."""
        import span.voice.server as server_module

        mock_config = MagicMock()
        mock_config.daily_api_key = None

        orig_config = server_module.config
        orig_db = server_module.db

        try:
            server_module.config = mock_config
            server_module.db = MagicMock()

            client = TestClient(app)
            response = client.get("/web")

            assert response.status_code == 200
            assert "error" in response.json()
            assert "DAILY_API_KEY" in response.json()["error"]
        finally:
            server_module.config = orig_config
            server_module.db = orig_db

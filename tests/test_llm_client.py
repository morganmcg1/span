"""Tests for Claude API wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from span.llm.client import ClaudeClient, Message


class TestMessageDataclass:
    """Tests for the Message dataclass."""

    def test_message_creation(self):
        """Message should store role and content."""
        msg = Message(role="user", content="Hola")
        assert msg.role == "user"
        assert msg.content == "Hola"


class TestClaudeClientInit:
    """Tests for ClaudeClient initialization."""

    @patch("anthropic.Anthropic")
    def test_init_creates_client(self, mock_anthropic):
        """Should create Anthropic client with API key."""
        client = ClaudeClient(api_key="test-key")
        mock_anthropic.assert_called_once_with(api_key="test-key")

    @patch("anthropic.Anthropic")
    def test_init_stores_model(self, mock_anthropic):
        """Should store the model name."""
        client = ClaudeClient(api_key="test-key", model="claude-test")
        assert client.model == "claude-test"

    @patch("anthropic.Anthropic")
    def test_init_uses_default_model(self, mock_anthropic):
        """Should use default model if not specified."""
        client = ClaudeClient(api_key="test-key")
        assert "claude" in client.model.lower()


class TestClaudeClientChat:
    """Tests for the chat method."""

    @patch("anthropic.Anthropic")
    def test_chat_formats_messages(self, mock_anthropic):
        """Should format Message objects to dicts."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.chat([Message(role="user", content="Hello")])

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hello"}]

    @patch("anthropic.Anthropic")
    def test_chat_includes_system_prompt(self, mock_anthropic):
        """Should include system prompt when provided."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.chat(
            [Message(role="user", content="Hello")],
            system="Be helpful",
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "Be helpful"

    @patch("anthropic.Anthropic")
    def test_chat_omits_system_when_none(self, mock_anthropic):
        """Should not include system key when None."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.chat([Message(role="user", content="Hello")])

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "system" not in call_kwargs

    @patch("anthropic.Anthropic")
    def test_chat_returns_response_text(self, mock_anthropic):
        """Should return the text from response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="¡Hola! ¿Cómo estás?")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        result = client.chat([Message(role="user", content="Hi")])

        assert result == "¡Hola! ¿Cómo estás?"

    @patch("anthropic.Anthropic")
    def test_chat_uses_max_tokens(self, mock_anthropic):
        """Should pass max_tokens to API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.chat([Message(role="user", content="Hello")], max_tokens=500)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 500


class TestAssessSpanishResponse:
    """Tests for assess_spanish_response method."""

    @patch("anthropic.Anthropic")
    def test_assess_parses_score_and_feedback(self, mock_anthropic):
        """Should parse SCORE and FEEDBACK from response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: 4\nFEEDBACK: Good job!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        score, feedback = client.assess_spanish_response(
            user_spanish="Hola, ¿qué onda?",
            context="Greeting practice",
        )

        assert score == 4
        assert feedback == "Good job!"

    @patch("anthropic.Anthropic")
    def test_assess_clamps_score_above_five(self, mock_anthropic):
        """Should clamp scores above 5."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: 10\nFEEDBACK: Perfect!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        score, _ = client.assess_spanish_response(
            user_spanish="Hola",
            context="Test",
        )

        assert score == 5

    @patch("anthropic.Anthropic")
    def test_assess_clamps_score_below_zero(self, mock_anthropic):
        """Should clamp scores below 0."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: -5\nFEEDBACK: Keep trying!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        score, _ = client.assess_spanish_response(
            user_spanish="Wrong",
            context="Test",
        )

        assert score == 0

    @patch("anthropic.Anthropic")
    def test_assess_handles_malformed_response(self, mock_anthropic):
        """Should handle responses without proper format."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This response has no proper format")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        score, feedback = client.assess_spanish_response(
            user_spanish="Test",
            context="Test",
        )

        # Should use defaults
        assert score == 3
        assert "This response has no proper format" in feedback

    @patch("anthropic.Anthropic")
    def test_assess_handles_non_numeric_score(self, mock_anthropic):
        """Should handle non-numeric score gracefully."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: excellent\nFEEDBACK: Great!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        score, _ = client.assess_spanish_response(
            user_spanish="Test",
            context="Test",
        )

        assert score == 3  # default

    @patch("anthropic.Anthropic")
    def test_assess_includes_vocabulary_in_context(self, mock_anthropic):
        """Should include expected vocabulary in system prompt."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="SCORE: 5\nFEEDBACK: Perfect!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.assess_spanish_response(
            user_spanish="Test",
            context="Test",
            expected_vocabulary=["hola", "adios"],
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "hola" in call_kwargs["system"]
        assert "adios" in call_kwargs["system"]


class TestGenerateConversationPrompt:
    """Tests for generate_conversation_prompt method."""

    @patch("anthropic.Anthropic")
    def test_generate_includes_topic_in_prompt(self, mock_anthropic):
        """Should include topic in the prompt."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="¡Hola!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.generate_conversation_prompt(
            topic="greetings",
            vocabulary=["hola"],
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_message = call_kwargs["messages"][0]["content"]
        assert "greetings" in user_message

    @patch("anthropic.Anthropic")
    def test_generate_includes_vocabulary(self, mock_anthropic):
        """Should include vocabulary in the prompt."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="¡Hola!")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        client.generate_conversation_prompt(
            topic="greetings",
            vocabulary=["hola", "adios"],
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_message = call_kwargs["messages"][0]["content"]
        assert "hola" in user_message
        assert "adios" in user_message

    @patch("anthropic.Anthropic")
    def test_generate_returns_response(self, mock_anthropic):
        """Should return the generated prompt."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="¡Hola! ¿Cómo estás hoy?")]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = ClaudeClient(api_key="test-key")
        result = client.generate_conversation_prompt(
            topic="greetings",
            vocabulary=["hola"],
        )

        assert result == "¡Hola! ¿Cómo estás hoy?"

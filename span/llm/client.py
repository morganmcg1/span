"""Anthropic Claude client wrapper."""

from dataclasses import dataclass, field

import anthropic


@dataclass
class Message:
    """A conversation message."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class ButtonOption:
    """A button option for the user to click."""

    label: str
    value: str


@dataclass
class ChatResponse:
    """Response from Claude, possibly with interactive buttons."""

    text: str
    buttons: list[ButtonOption] = field(default_factory=list)


# Tool definition for presenting options to the user
PRESENT_OPTIONS_TOOL = {
    "name": "present_options",
    "description": (
        "Present clickable button options to the learner. Use this when asking yes/no questions, "
        "offering choices (like which topic to practice), or when the learner needs to pick from "
        "specific options. The buttons appear below your message. Use sparingly - only when choices "
        "are clear and discrete. Max 4 options."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "Button text shown to user (keep short, 1-4 words)",
                        },
                        "value": {
                            "type": "string",
                            "description": "Value sent back when clicked (can be same as label)",
                        },
                    },
                    "required": ["label", "value"],
                },
                "minItems": 2,
                "maxItems": 4,
                "description": "The options to present as buttons",
            },
        },
        "required": ["options"],
    },
}


class ClaudeClient:
    """Wrapper for Anthropic's Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Send a conversation to Claude and get a response."""
        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": formatted_messages,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def chat_with_buttons(
        self,
        messages: list[Message],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> ChatResponse:
        """Chat with Claude, allowing it to present button options."""
        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": formatted_messages,
            "tools": [PRESENT_OPTIONS_TOOL],
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)

        # Extract text and any button tool calls
        text_parts = []
        buttons = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use" and block.name == "present_options":
                # Extract button options from tool call
                options = block.input.get("options", [])
                for opt in options:
                    buttons.append(ButtonOption(
                        label=opt.get("label", ""),
                        value=opt.get("value", opt.get("label", "")),
                    ))

        return ChatResponse(
            text="\n".join(text_parts),
            buttons=buttons,
        )

    def assess_spanish_response(
        self,
        user_spanish: str,
        context: str,
        expected_vocabulary: list[str] | None = None,
    ) -> tuple[int, str]:
        """
        Assess a user's Spanish response.

        Returns:
            tuple of (quality_score 0-5, feedback_text)
        """
        vocab_context = ""
        if expected_vocabulary:
            vocab_context = f"\nVocabulary being practiced: {', '.join(expected_vocabulary)}"

        system = f"""You are evaluating a Spanish learner's response.
Context: {context}{vocab_context}

Rate the response on a scale of 0-5:
5 - Perfect, natural Mexican Spanish
4 - Correct with minor issues
3 - Understandable but with noticeable errors
2 - Attempted but significant errors
1 - Mostly incorrect
0 - No attempt or completely wrong

Respond in this exact format:
SCORE: [0-5]
FEEDBACK: [Brief, encouraging feedback in English with specific corrections if needed]"""

        response = self.chat(
            messages=[Message(role="user", content=f"Student's response: {user_spanish}")],
            system=system,
            max_tokens=200,
        )

        # Parse response
        lines = response.strip().split("\n")
        score = 3  # default
        feedback = response

        for line in lines:
            if line.startswith("SCORE:"):
                try:
                    score = int(line.replace("SCORE:", "").strip())
                    score = max(0, min(5, score))
                except ValueError:
                    pass
            elif line.startswith("FEEDBACK:"):
                feedback = line.replace("FEEDBACK:", "").strip()

        return score, feedback

    def generate_conversation_prompt(
        self,
        topic: str,
        vocabulary: list[str],
        user_level: str = "beginner-intermediate",
    ) -> str:
        """Generate a conversation starter for the voice lesson."""
        system = """Generate a natural conversation starter for a Spanish tutor to use with a student.
The tutor should speak in Spanish but be ready to explain in English.
Keep it casual and Mexican in style."""

        prompt = f"""Topic: {topic}
Vocabulary to naturally incorporate: {', '.join(vocabulary)}
Student level: {user_level}

Generate a friendly opening line (in Spanish) and a simple question to get the conversation started."""

        return self.chat(
            messages=[Message(role="user", content=prompt)],
            system=system,
            max_tokens=150,
        )

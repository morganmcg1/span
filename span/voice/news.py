"""News story fetching for conversation lessons using OpenAI Responses API with web search."""

import asyncio
from pydantic import BaseModel

from openai import OpenAI


class VocabItem(BaseModel):
    """A vocabulary item extracted from the news story."""

    spanish: str
    english: str
    usage_note: str  # How this word is used in Mexican Spanish context


class GrammarPoint(BaseModel):
    """A grammar structure that could be practiced from the story."""

    structure: str  # e.g., "preterite vs imperfect"
    example: str  # Example sentence from the story
    explanation: str  # Brief explanation of the grammar point


class NewsStory(BaseModel):
    """A news story prepared for language learning discussion."""

    headline: str
    summary_for_teacher: str  # Full context for the teacher
    summary_for_student: str  # Brief 10-20 second verbal summary
    source: str
    vocab_items: list[VocabItem]
    grammar_points: list[GrammarPoint]
    discussion_questions: list[str]


NEWS_SEARCH_PROMPT = """You are helping a Mexican Spanish language tutor prepare a news-based conversation lesson.

Your task:
1. Search for interesting news from today (or very recent)
2. Pick ONE story that would be good for language learning discussion:
   - Preferably something with human interest, culture, science, or positive news
   - Avoid overly complex political or financial topics
   - Stories about Mexico, Latin America, or Spanish-speaking world are great
   - Universal topics (sports, entertainment, technology) also work well

3. For the chosen story, extract:
   - A clear headline
   - A full summary for the teacher's context (2-3 paragraphs)
   - A brief summary for telling the student verbally (should take 10-20 seconds to say)
   - The source URL or publication name
   - 3-5 vocabulary items that would be useful for a Spanish learner, with Mexican Spanish context
   - 1-2 grammar points that could naturally come up discussing this story
   - 2-3 discussion questions to ask the student

Focus on vocabulary that's:
- Relevant to the story topic
- Useful in everyday Mexican Spanish conversation
- At an intermediate level (not too basic, not too advanced)

For grammar, focus on structures like:
- Past tense narration (preterite vs imperfect)
- Expressing opinions ("me parece que...", "creo que...")
- Conditionals ("si yo fuera...", "hubiera...")
- Subjunctive in common contexts"""


async def fetch_news_story(openai_api_key: str) -> NewsStory:
    """Fetch a news story suitable for language learning discussion.

    Uses OpenAI Responses API with web search to find and analyze
    a current news story, extracting vocabulary and grammar points.

    Args:
        openai_api_key: OpenAI API key

    Returns:
        NewsStory with headline, summaries, vocab, grammar, and questions
    """
    client = OpenAI(api_key=openai_api_key)

    # Run synchronous API call in thread pool to avoid blocking
    def _fetch():
        response = client.responses.parse(
            model="gpt-5.2",
            tools=[{"type": "web_search"}],
            input=NEWS_SEARCH_PROMPT,
            text_format=NewsStory,
        )
        return response.output_parsed

    story = await asyncio.to_thread(_fetch)
    return story

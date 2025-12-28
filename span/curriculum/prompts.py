"""Prompt type system for adaptive curriculum.

Implements Matuschak's prompt progression:
- Recognition: Can you understand this?
- Cued Production: Can you produce this with a hint?
- Free Production: Can you produce this without help?
- Application: Can you use this in a novel context?

Each prompt type requires different levels of mastery and develops
different aspects of language competence.
"""

from dataclasses import dataclass

from span.db.models import CurriculumItem, SkillDimensions, SkillLevel


class PromptType:
    """Prompt types in order of difficulty."""

    RECOGNITION = "recognition"  # Understand Spanish → English
    CUED_PRODUCTION = "cued_production"  # Produce with hint
    FREE_PRODUCTION = "free_production"  # Produce without hint
    APPLICATION = "application"  # Use in novel context


@dataclass
class PromptTemplate:
    """Template for generating prompts of a specific type."""

    prompt_type: str
    template: str
    answer_template: str
    hint_template: str | None = None


# Prompt templates for different types
PROMPT_TEMPLATES = {
    PromptType.RECOGNITION: PromptTemplate(
        prompt_type=PromptType.RECOGNITION,
        template="What does '{spanish}' mean?",
        answer_template="{english}",
        hint_template="Topic: {topic}. {mexican_notes}",
    ),
    PromptType.CUED_PRODUCTION: PromptTemplate(
        prompt_type=PromptType.CUED_PRODUCTION,
        template="How would you say '{english}' in Mexican Spanish? (hint: {hint})",
        answer_template="{spanish}",
        hint_template="Starts with: {first_word}",
    ),
    PromptType.FREE_PRODUCTION: PromptTemplate(
        prompt_type=PromptType.FREE_PRODUCTION,
        template="How would you say '{english}' in Mexican Spanish?",
        answer_template="{spanish}",
    ),
    PromptType.APPLICATION: PromptTemplate(
        prompt_type=PromptType.APPLICATION,
        template="{scenario}",
        answer_template="Use: {spanish} ({english})",
    ),
}


# Application scenarios for items (keyed by topic)
APPLICATION_SCENARIOS = {
    "greetings": [
        "You bump into a friend on the street. How do you greet them casually?",
        "Your phone rings. How do you answer it?",
        "You're being introduced to someone. What do you say?",
        "Someone called your name but you didn't hear what they said. How do you respond?",
    ],
    "expressions": [
        "Your friend tells you they won the lottery. How do you express surprise?",
        "Someone suggests going to the beach. How do you say 'sounds good'?",
        "You see your friend's new car and think it's really cool. What do you say?",
        "Someone asks if you really did something. How do you confirm it's true?",
    ],
    "food": [
        "You're at a restaurant and want to pay. How do you ask for the check?",
        "You want the waiter to suggest something good. What do you ask?",
        "You're craving street food. How do you suggest getting some?",
    ],
    "transport": [
        "You're in a taxi and want to get off at the next corner. What do you say?",
        "You want to know how much the Uber will cost. How do you ask?",
        "You're asking about taking public transport. What type of vehicle might you mention?",
    ],
    "money": [
        "You're at a market and want to know the price of avocados. How do you ask?",
        "Your friend asks if you have cash. How do you say you don't?",
        "You need change for the bus. How do you ask if someone has some?",
    ],
    "fillers": [
        "You're thinking about how to respond and need to fill the silence. What do you say?",
        "You want to clarify or rephrase what you just said. What filler do you use?",
        "You're starting a sentence and need a casual opener. What do you say?",
    ],
    "texting": [
        "You're texting a friend to say 'don't worry'. What abbreviation do you use?",
        "You want to text 'I love you' to a close friend. What's the shorthand?",
        "Someone texts you asking why. What quick response do you type?",
    ],
    "storytelling": [
        "Your friend asks what you did yesterday. Start telling them the story.",
        "Something funny happened to you at the supermarket. How do you begin the story?",
        "You want to tell a story about meeting someone. How do you start?",
        "You're in the middle of a story and want to build suspense. What do you say?",
        "You're wrapping up an exciting story. How do you end it?",
    ],
    "conditionals": [
        "Your friend is unsure about taking a job. Give them advice starting with 'if I were you'.",
        "Someone asks what you would do if you won the lottery. How do you respond?",
        "You want to express a wish about speaking Spanish better. What do you say?",
        "You can't help a friend right now. How do you politely explain using a conditional?",
        "You want to suggest meeting up more often. How do you phrase it politely?",
    ],
}


def select_prompt_type_for_item(
    skills: SkillDimensions,
    item: CurriculumItem,
    item_repetitions: int = 0,
) -> str:
    """Select the appropriate prompt type based on mastery level.

    Args:
        skills: Current skill dimensions
        item: The curriculum item
        item_repetitions: Number of times this item has been reviewed

    Returns:
        Prompt type: 'recognition', 'cued_production', 'free_production', 'application'
    """
    # Get the primary skill this item develops
    primary_skill = None
    primary_level = 1

    if item.skill_contributions:
        # Find the skill with the highest target level
        for skill_name, target_level in item.skill_contributions.items():
            current_level = getattr(skills, skill_name, 1)
            if target_level > primary_level:
                primary_level = target_level
                primary_skill = skill_name

    # Determine prompt type based on item repetitions and skill level
    if item_repetitions == 0:
        # First encounter: always recognition
        return PromptType.RECOGNITION
    elif item_repetitions <= 2:
        # Learning phase: cued production
        return PromptType.CUED_PRODUCTION
    elif item_repetitions <= 5:
        # Consolidation: free production
        return PromptType.FREE_PRODUCTION
    else:
        # Mastery: application if available
        if "application" in (item.prompt_types or []):
            return PromptType.APPLICATION
        return PromptType.FREE_PRODUCTION


def generate_prompt(
    item: CurriculumItem,
    prompt_type: str,
    include_hint: bool = False,
) -> dict:
    """Generate a prompt for a curriculum item.

    Args:
        item: The curriculum item
        prompt_type: Type of prompt to generate
        include_hint: Whether to include a hint

    Returns:
        Dict with 'prompt', 'answer', and optionally 'hint'
    """
    template = PROMPT_TEMPLATES.get(prompt_type, PROMPT_TEMPLATES[PromptType.RECOGNITION])

    # Get first word for cued production hint
    first_word = item.spanish.split()[0] if item.spanish else ""

    # Format the prompt
    if prompt_type == PromptType.APPLICATION:
        # Select a scenario for application prompts
        scenarios = APPLICATION_SCENARIOS.get(item.topic, [])
        if scenarios:
            import random
            scenario = random.choice(scenarios)
        else:
            # Fallback to free production if no scenarios
            return generate_prompt(item, PromptType.FREE_PRODUCTION, include_hint)

        prompt = template.template.format(scenario=scenario)
    else:
        prompt = template.template.format(
            spanish=item.spanish,
            english=item.english,
            hint=first_word if prompt_type == PromptType.CUED_PRODUCTION else "",
        )

    answer = template.answer_template.format(
        spanish=item.spanish,
        english=item.english,
    )

    result = {
        "prompt": prompt,
        "answer": answer,
        "prompt_type": prompt_type,
        "item_id": item.id,
    }

    # Add hint if requested and available
    if include_hint and template.hint_template:
        hint = template.hint_template.format(
            topic=item.topic,
            mexican_notes=item.mexican_notes or "",
            first_word=first_word,
        )
        result["hint"] = hint

    return result


def generate_voice_prompt(
    item: CurriculumItem,
    prompt_type: str,
) -> str:
    """Generate a voice-friendly prompt for the tutor to speak.

    These prompts are designed to be spoken naturally in conversation.
    """
    if prompt_type == PromptType.RECOGNITION:
        return f"Do you know what '{item.spanish}' means?"

    elif prompt_type == PromptType.CUED_PRODUCTION:
        first_word = item.spanish.split()[0] if item.spanish else ""
        return f"How would you say '{item.english}'? It starts with '{first_word}'..."

    elif prompt_type == PromptType.FREE_PRODUCTION:
        return f"How would you say '{item.english}' in Spanish?"

    elif prompt_type == PromptType.APPLICATION:
        scenarios = APPLICATION_SCENARIOS.get(item.topic, [])
        if scenarios:
            import random
            scenario = random.choice(scenarios)
            return scenario
        return f"Can you use '{item.spanish}' in a sentence?"

    return f"What does '{item.spanish}' mean?"


def get_feedback_for_response(
    item: CurriculumItem,
    user_response: str,
    quality: int,
    prompt_type: str,
) -> str:
    """Generate feedback based on the user's response quality.

    Args:
        item: The curriculum item
        user_response: What the user said
        quality: Quality score 0-5
        prompt_type: Type of prompt that was given

    Returns:
        Feedback string for the tutor to say
    """
    if quality >= 5:
        return f"Perfect! '{item.spanish}' means '{item.english}'."
    elif quality >= 4:
        return f"Very good! Just a small hesitation. '{item.spanish}' - '{item.english}'."
    elif quality >= 3:
        return f"Good effort! The answer is '{item.spanish}' - '{item.english}'. {item.mexican_notes or ''}"
    elif quality >= 2:
        return f"Close! The correct answer is '{item.spanish}'. Remember: {item.english}."
    else:
        return f"Let me help you. '{item.spanish}' means '{item.english}'. {item.mexican_notes or ''}"

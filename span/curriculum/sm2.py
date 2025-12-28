"""SM-2 Spaced Repetition Algorithm.

Based on the SuperMemo SM-2 algorithm by Piotr Wozniak.
https://www.supermemo.com/en/blog/application-of-a-computer-to-improve-the-results-obtained-in-working-with-the-supermemo-method
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SM2Result:
    """Result of an SM-2 calculation."""

    easiness_factor: float
    interval_days: int
    repetitions: int
    next_review: datetime


def calculate_sm2(
    quality: int,
    easiness_factor: float = 2.5,
    interval_days: int = 0,
    repetitions: int = 0,
) -> SM2Result:
    """
    Calculate the next review interval using the SM-2 algorithm.

    Args:
        quality: Response quality (0-5):
            5 - Perfect response, no hesitation
            4 - Correct response after hesitation
            3 - Correct response with difficulty
            2 - Incorrect, but seemed easy to recall
            1 - Incorrect, but remembered when shown answer
            0 - Complete blackout

        easiness_factor: Current easiness factor (default 2.5)
        interval_days: Current interval in days
        repetitions: Number of consecutive correct responses

    Returns:
        SM2Result with updated values and next review date.
    """
    # Clamp quality to valid range
    quality = max(0, min(5, quality))

    # Update easiness factor
    new_ef = easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)  # Minimum EF is 1.3

    if quality >= 3:
        # Correct response - increase interval
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * new_ef)
        new_repetitions = repetitions + 1
    else:
        # Incorrect response - reset to beginning
        new_interval = 1
        new_repetitions = 0
        # Keep the lowered EF

    return SM2Result(
        easiness_factor=new_ef,
        interval_days=new_interval,
        repetitions=new_repetitions,
        next_review=datetime.now() + timedelta(days=new_interval),
    )


def quality_from_performance(correct: bool, response_time_ms: int | None = None) -> int:
    """
    Convert a simple correct/incorrect + optional response time to SM-2 quality.

    Args:
        correct: Whether the response was correct
        response_time_ms: Optional response time in milliseconds

    Returns:
        Quality score 0-5
    """
    if not correct:
        return 1  # Incorrect but shown answer

    if response_time_ms is None:
        return 4  # Correct, assume some hesitation

    # Fast response = perfect, slow = difficulty
    if response_time_ms < 2000:
        return 5  # Perfect
    elif response_time_ms < 5000:
        return 4  # Hesitation
    else:
        return 3  # Difficulty

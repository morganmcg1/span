"""Tests for the SM-2 spaced repetition algorithm."""

from datetime import datetime, timedelta

import pytest

from span.curriculum.sm2 import calculate_sm2, quality_from_performance, SM2Result


class TestSM2Algorithm:
    """Tests for the SM-2 algorithm."""

    def test_first_correct_response(self):
        """First correct response should set interval to 1 day."""
        result = calculate_sm2(quality=4)
        assert result.interval_days == 1
        assert result.repetitions == 1
        assert result.easiness_factor >= 2.3

    def test_second_correct_response(self):
        """Second correct response should set interval to 6 days."""
        result = calculate_sm2(quality=4, repetitions=1, interval_days=1)
        assert result.interval_days == 6
        assert result.repetitions == 2

    def test_third_correct_response(self):
        """Third correct response should multiply by easiness factor."""
        result = calculate_sm2(
            quality=4,
            repetitions=2,
            interval_days=6,
            easiness_factor=2.5,
        )
        # 6 * 2.5 = 15 (but EF changes slightly)
        assert result.interval_days >= 10
        assert result.repetitions == 3

    def test_incorrect_response_resets(self):
        """Incorrect response should reset repetitions."""
        result = calculate_sm2(
            quality=2,
            repetitions=5,
            interval_days=30,
            easiness_factor=2.5,
        )
        assert result.interval_days == 1
        assert result.repetitions == 0

    def test_perfect_response_increases_easiness(self):
        """Perfect response (5) should increase easiness factor."""
        result = calculate_sm2(quality=5, easiness_factor=2.5)
        assert result.easiness_factor > 2.5

    def test_difficult_response_decreases_easiness(self):
        """Difficult response (3) should decrease easiness factor."""
        result = calculate_sm2(quality=3, easiness_factor=2.5)
        assert result.easiness_factor < 2.5

    def test_easiness_factor_minimum(self):
        """Easiness factor should not go below 1.3."""
        result = calculate_sm2(quality=0, easiness_factor=1.5)
        assert result.easiness_factor >= 1.3

    def test_next_review_date(self):
        """Next review date should be in the future."""
        result = calculate_sm2(quality=4)
        assert result.next_review > datetime.now()

    def test_quality_clamp(self):
        """Quality should be clamped to 0-5 range."""
        result_high = calculate_sm2(quality=10)
        result_low = calculate_sm2(quality=-5)
        # Both should work without error
        assert result_high.interval_days >= 1
        assert result_low.interval_days >= 1


class TestQualityFromPerformance:
    """Tests for converting performance to quality score."""

    def test_incorrect_returns_low_score(self):
        """Incorrect response should return 1."""
        assert quality_from_performance(correct=False) == 1

    def test_fast_correct_is_perfect(self):
        """Fast correct response should be perfect (5)."""
        assert quality_from_performance(correct=True, response_time_ms=1000) == 5

    def test_medium_correct_is_hesitation(self):
        """Medium speed correct response is hesitation (4)."""
        assert quality_from_performance(correct=True, response_time_ms=3000) == 4

    def test_slow_correct_is_difficulty(self):
        """Slow correct response shows difficulty (3)."""
        assert quality_from_performance(correct=True, response_time_ms=7000) == 3

    def test_no_time_defaults_to_hesitation(self):
        """Correct with no time info defaults to hesitation (4)."""
        assert quality_from_performance(correct=True) == 4

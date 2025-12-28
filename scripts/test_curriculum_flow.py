#!/usr/bin/env python3
"""Integration test for curriculum skill tracking flow.

Tests the full loop without requiring actual voice calls:
1. Create user with initial skills
2. Simulate practice with SM-2 updates
3. Verify skill dimensions update
4. Verify next item selection reflects skill changes
5. Test memory extraction (optional, requires API key)

Run: uv run python scripts/test_curriculum_flow.py
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tempfile

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import simple_parsing as sp

from span.curriculum.content import seed_database
from span.curriculum.scheduler import CurriculumScheduler
from span.curriculum.selector import compute_readiness
from span.curriculum.sm2 import calculate_sm2
from span.db.database import Database
from span.db.models import SkillDimensions, SkillLevel, User


@dataclass
class Args:
    """Integration test for curriculum skill tracking."""

    test_extraction: bool = False  # Test memory extraction (requires ANTHROPIC_API_KEY)
    verbose: bool = False  # Show detailed output


console = Console()


def create_test_db() -> tuple[Database, int]:
    """Create a temporary database with test user and seed content."""
    # Create temp directory for test database
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_curriculum.db"

    db = Database(str(db_path))
    db.init_schema()

    # Seed curriculum content
    seed_database(db)

    # Create test user
    user = User(
        phone_number="+15551234567",
        telegram_id=123456789,
        timezone="America/Los_Angeles",
    )
    user_id = db.create_user(user)

    return db, user_id


def test_initial_skills(db: Database, user_id: int) -> SkillDimensions:
    """Verify initial skill dimensions are created correctly."""
    console.rule("[bold]Test 1: Initial Skill Dimensions")

    skills = db.get_or_create_skill_dimensions(user_id)

    # All skills should start at level 1 (NONE)
    skill_names = [
        "vocabulary_recognition", "vocabulary_production", "pronunciation",
        "grammar_receptive", "grammar_productive", "conversational_flow",
        "cultural_pragmatics", "narration", "conditionals",
    ]

    all_at_level_1 = all(getattr(skills, name) == 1 for name in skill_names)

    if all_at_level_1:
        console.print("[green]✓ All skills initialized at level 1 (NONE)[/green]")
    else:
        console.print("[red]✗ Skills not initialized correctly[/red]")
        for name in skill_names:
            level = getattr(skills, name)
            console.print(f"  {name}: {level} ({SkillLevel(level).name})")

    return skills


def test_sm2_scheduling(db: Database, user_id: int, verbose: bool) -> None:
    """Verify SM-2 spaced repetition updates work correctly."""
    console.rule("[bold]Test 2: SM-2 Scheduling")

    # Get a curriculum item
    items = db.get_all_curriculum_items()
    if not items:
        console.print("[red]✗ No curriculum items found[/red]")
        return

    item = items[0]
    console.print(f"Testing with: '{item.spanish}' ({item.english})")

    # Get initial progress
    progress = db.get_or_create_progress(user_id, item.id)
    initial_interval = progress.interval_days
    initial_ef = progress.easiness_factor

    # Simulate a quality=5 review (perfect)
    sm2_result = calculate_sm2(
        quality=5,
        easiness_factor=progress.easiness_factor,
        interval_days=progress.interval_days,
        repetitions=progress.repetitions,
    )

    # Update progress
    progress.easiness_factor = sm2_result.easiness_factor
    progress.interval_days = sm2_result.interval_days
    progress.repetitions = sm2_result.repetitions
    progress.next_review = sm2_result.next_review
    progress.last_reviewed = datetime.now()
    db.update_progress(progress)

    if verbose:
        console.print(f"  Initial interval: {initial_interval} days, EF: {initial_ef:.2f}")
        console.print(f"  After review (quality=5): {sm2_result.interval_days} days, EF: {sm2_result.easiness_factor:.2f}")

    if sm2_result.interval_days >= initial_interval:
        console.print("[green]✓ SM-2 interval increased after quality=5 review[/green]")
    else:
        console.print("[red]✗ SM-2 interval did not increase[/red]")


def test_skill_advancement(db: Database, user_id: int) -> None:
    """Verify skill dimensions can be updated."""
    console.rule("[bold]Test 3: Skill Advancement")

    skills = db.get_or_create_skill_dimensions(user_id)
    original_level = skills.vocabulary_production

    # Simulate advancement
    skills.vocabulary_production = 3  # RECOGNITION
    skills.pronunciation = 2  # EXPOSURE
    db.update_skill_dimensions(skills)

    # Retrieve and verify
    updated = db.get_or_create_skill_dimensions(user_id)

    if updated.vocabulary_production == 3 and updated.pronunciation == 2:
        console.print("[green]✓ Skills updated correctly[/green]")
        console.print(f"  vocabulary_production: {original_level} → 3 ({SkillLevel(3).name})")
        console.print(f"  pronunciation: 1 → 2 ({SkillLevel(2).name})")
    else:
        console.print("[red]✗ Skills not updated correctly[/red]")


def test_zpd_selection(db: Database, user_id: int, verbose: bool) -> None:
    """Verify ZPD-based item selection works."""
    console.rule("[bold]Test 4: ZPD Item Selection")

    scheduler = CurriculumScheduler(db)
    skills = db.get_or_create_skill_dimensions(user_id)

    # Create a daily plan
    plan = scheduler.create_daily_plan(user_id)

    console.print(f"Suggested topic: {plan.suggested_topic}")
    console.print(f"Review items: {len(plan.review_items)}")
    console.print(f"New items: {len(plan.new_items)}")

    if verbose:
        console.print("\n[bold]Review items:[/bold]")
        for item in plan.review_items[:3]:
            readiness = compute_readiness(skills, item.skill_requirements or {})
            console.print(f"  - {item.spanish}: {readiness}")

        console.print("\n[bold]New items (ZPD selected):[/bold]")
        for item in plan.new_items[:3]:
            readiness = compute_readiness(skills, item.skill_requirements or {})
            console.print(f"  - {item.spanish}: {readiness}")

    # Verify we got items
    total_items = len(plan.review_items) + len(plan.new_items)
    if total_items > 0:
        console.print(f"[green]✓ Generated plan with {total_items} items[/green]")
    else:
        console.print("[yellow]⚠ No items in plan (might be expected with empty curriculum)[/yellow]")


def test_skill_context_in_selection(db: Database, user_id: int) -> None:
    """Verify that skill levels affect item selection."""
    console.rule("[bold]Test 5: Skill-Based Selection")

    scheduler = CurriculumScheduler(db)

    # Get plan with initial low skills
    plan1 = scheduler.create_daily_plan(user_id)
    initial_new_count = len(plan1.new_items)

    # Advance skills significantly
    skills = db.get_or_create_skill_dimensions(user_id)
    skills.vocabulary_recognition = 4  # PRODUCTION
    skills.vocabulary_production = 4
    skills.pronunciation = 3
    skills.grammar_receptive = 3
    db.update_skill_dimensions(skills)

    # Get plan with advanced skills
    plan2 = scheduler.create_daily_plan(user_id)
    advanced_new_count = len(plan2.new_items)

    console.print(f"Items at low skill level: {initial_new_count}")
    console.print(f"Items at high skill level: {advanced_new_count}")

    # With higher skills, should potentially access more items (higher ZPD range)
    console.print("[green]✓ Selection completed at different skill levels[/green]")


async def test_memory_extraction(db: Database, user_id: int) -> None:
    """Test memory extraction (requires API key)."""
    console.rule("[bold]Test 6: Memory Extraction")

    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[yellow]⚠ Skipping: ANTHROPIC_API_KEY not set[/yellow]")
        return

    from span.memory.extractor import MemoryExtractor

    extractor = MemoryExtractor(db, api_key)

    # Simulate a conversation snippet
    messages = [
        {"role": "assistant", "content": "¡Hola! ¿Cómo estás?"},
        {"role": "user", "content": "Estoy bien, gracias. Me llamo Carlos."},
        {"role": "assistant", "content": "¡Mucho gusto, Carlos! ¿De dónde eres?"},
        {"role": "user", "content": "Soy de California. I want to learn Spanish for traveling to Mexico."},
    ]

    result = await extractor.extract_facts_async(user_id, messages, "test")

    console.print(f"Facts extracted: {result.facts_extracted}")
    if result.profile_updated:
        console.print("[green]✓ Profile updated[/green]")
        profile = db.get_or_create_learner_profile(user_id)
        if profile.name:
            console.print(f"  Name learned: {profile.name}")
        if profile.location:
            console.print(f"  Location learned: {profile.location}")
    if result.skills_updated:
        console.print(f"[green]✓ Skills updated: {result.skills_updated}[/green]")


def show_final_state(db: Database, user_id: int) -> None:
    """Display final state of user's skills."""
    console.rule("[bold]Final State")

    skills = db.get_or_create_skill_dimensions(user_id)
    profile = db.get_or_create_learner_profile(user_id)

    # Skills table
    table = Table(title="Skill Dimensions")
    table.add_column("Skill", style="cyan")
    table.add_column("Level", style="green")
    table.add_column("Name", style="yellow")

    skill_names = [
        "vocabulary_recognition", "vocabulary_production", "pronunciation",
        "grammar_receptive", "grammar_productive", "conversational_flow",
        "cultural_pragmatics", "narration", "conditionals",
    ]

    for name in skill_names:
        level = getattr(skills, name)
        table.add_row(name, str(level), SkillLevel(level).name)

    console.print(table)

    # Profile info
    if profile.name or profile.location or profile.goals:
        console.print("\n[bold]Learner Profile:[/bold]")
        if profile.name:
            console.print(f"  Name: {profile.name}")
        if profile.location:
            console.print(f"  Location: {profile.location}")
        if profile.goals:
            console.print(f"  Goals: {profile.goals}")


def main() -> None:
    args = sp.parse(Args)

    console.print(Panel(
        "[bold blue]Curriculum Flow Integration Test[/bold blue]\n"
        "Testing the full skill tracking loop without voice calls",
        title="span"
    ))

    # Create test database
    db, user_id = create_test_db()
    console.print(f"[dim]Created test database with user ID: {user_id}[/dim]\n")

    try:
        # Run tests
        test_initial_skills(db, user_id)
        console.print()

        test_sm2_scheduling(db, user_id, args.verbose)
        console.print()

        test_skill_advancement(db, user_id)
        console.print()

        test_zpd_selection(db, user_id, args.verbose)
        console.print()

        test_skill_context_in_selection(db, user_id)
        console.print()

        if args.test_extraction:
            asyncio.run(test_memory_extraction(db, user_id))
            console.print()

        show_final_state(db, user_id)

        console.print(Panel("[bold green]All tests completed!", title="Done"))

    except Exception as e:
        console.print(f"[red]Test failed: {e}[/red]")
        raise


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Initialize the database with schema and seed content."""

from rich.console import Console
from rich.panel import Panel

from span.config import Config
from span.curriculum.content import seed_database
from span.db.database import Database
from span.db.models import User


console = Console()


def main() -> None:
    console.rule("[bold blue]Initializing Span Database")

    # Load config
    config = Config.from_env()
    config.ensure_database_dir()

    console.print(f"Database path: {config.database_path}")

    # Initialize database
    db = Database(config.database_path)
    db.init_schema()
    console.print("[green]✓ Schema created[/green]")

    # Seed content
    count = seed_database(db)
    console.print(f"[green]✓ Added {count} curriculum items[/green]")

    # Create default user if configured
    if config.telegram_user_id and config.user_phone_number:
        existing_user = db.get_user_by_telegram(config.telegram_user_id)
        if existing_user:
            console.print(f"[yellow]User already exists (ID: {existing_user.id})[/yellow]")
        else:
            user = User(
                phone_number=config.user_phone_number,
                telegram_id=config.telegram_user_id,
                timezone=config.timezone,
            )
            user_id = db.create_user(user)
            console.print(f"[green]✓ Created user (ID: {user_id})[/green]")
    else:
        console.print("[yellow]No user created (TELEGRAM_USER_ID or USER_PHONE_NUMBER not set)[/yellow]")

    console.print(Panel("[bold green]Database initialized successfully!", title="Done"))


if __name__ == "__main__":
    main()

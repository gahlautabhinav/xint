from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from rich.console import Console
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _default(obj: Any) -> Any:
    if isinstance(obj, (UUID, datetime)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=_default)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def print_jobs_table(jobs: list[Any], fmt: str) -> None:
    if fmt == "json":
        rows = [
            {
                "id": j.id,
                "seed_username": j.seed_username,
                "status": j.status.value,
                "accounts_scraped": j.accounts_scraped,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
            }
            for j in jobs
        ]
        console.print(dump_json(rows))
        return

    if not jobs:
        console.print("[dim]No jobs found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", width=8)
    table.add_column("Seed", min_width=12)
    table.add_column("Status", width=10)
    table.add_column("Scraped", justify="right", width=8)
    table.add_column("Created", width=20)

    for j in jobs:
        status_color = {
            "COMPLETED": "green",
            "RUNNING": "yellow",
            "FAILED": "red",
            "PENDING": "dim",
            "CANCELLED": "dim",
        }.get(j.status.value, "white")
        created = j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else "—"
        table.add_row(
            str(j.id)[:8],
            j.seed_username,
            f"[{status_color}]{j.status.value}[/{status_color}]",
            str(j.accounts_scraped),
            created,
        )
    console.print(table)


def print_job_detail(job: Any, events: list[Any], fmt: str) -> None:
    if fmt == "json":
        data = {
            "id": job.id,
            "seed_username": job.seed_username,
            "platform": job.platform,
            "status": job.status.value,
            "max_depth": job.max_depth,
            "max_accounts": job.max_accounts,
            "accounts_scraped": job.accounts_scraped,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "events": [
                {
                    "sequence": e.sequence,
                    "event_type": e.event_type,
                    "payload": e.payload,
                    "created_at": e.created_at,
                }
                for e in events
            ],
        }
        console.print(dump_json(data))
        return

    status_color = {
        "COMPLETED": "green",
        "RUNNING": "yellow",
        "FAILED": "red",
    }.get(job.status.value, "white")

    console.print(f"\n[bold]Job[/bold] [dim]{job.id}[/dim]")
    console.print(f"  Seed:     [bold]{job.seed_username}[/bold]")
    console.print(f"  Status:   [{status_color}]{job.status.value}[/{status_color}]")
    console.print(f"  Scraped:  {job.accounts_scraped} / {job.max_accounts}")
    console.print(f"  Depth:    {job.max_depth}")
    if job.error_message:
        console.print(f"  Error:    [red]{job.error_message}[/red]")

    if events:
        console.print(f"\n[bold]Events[/bold] ({len(events)} total):")
        for e in events[-10:]:
            ts = e.created_at.strftime("%H:%M:%S") if e.created_at else "?"
            console.print(f"  [{ts}] [dim]#{e.sequence}[/dim] {e.event_type}  {e.payload or ''}")


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def print_accounts_table(accounts: list[Any], fmt: str) -> None:
    if fmt == "json":
        rows = [
            {
                "id": a.id,
                "username": a.username,
                "platform": a.platform,
                "display_name": a.display_name,
                "followers_count": a.followers_count,
                "is_verified": a.is_verified,
                "scraped_at": a.scraped_at,
            }
            for a in accounts
        ]
        console.print(dump_json(rows))
        return

    if not accounts:
        console.print("[dim]No accounts found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Handle", min_width=16)
    table.add_column("Platform", width=9)
    table.add_column("Display Name", min_width=16)
    table.add_column("Followers", justify="right", width=10)
    table.add_column("✓", width=3)
    table.add_column("Scraped", width=20)

    for a in accounts:
        scraped = a.scraped_at.strftime("%Y-%m-%d %H:%M") if a.scraped_at else "—"
        table.add_row(
            f"@{a.username}",
            a.platform,
            a.display_name or "—",
            f"{a.followers_count:,}",
            "✓" if a.is_verified else "",
            scraped,
        )
    console.print(table)


def print_account_detail(account: Any, fmt: str) -> None:
    if fmt == "json":
        data = {
            "id": account.id,
            "username": account.username,
            "platform": account.platform,
            "display_name": account.display_name,
            "bio": account.bio,
            "website": account.website,
            "followers_count": account.followers_count,
            "following_count": account.following_count,
            "is_verified": account.is_verified,
            "scraped_at": account.scraped_at,
            "scrape_depth": account.scrape_depth,
        }
        console.print(dump_json(data))
        return

    console.print(f"\n[bold]@{account.username}[/bold] ({account.platform})")
    if account.display_name:
        console.print(f"  Name:      {account.display_name}")
    if account.bio:
        console.print(f"  Bio:       {account.bio[:100]}{'…' if len(account.bio or '') > 100 else ''}")
    if account.website:
        console.print(f"  Website:   {account.website}")
    console.print(f"  Followers: {account.followers_count:,}")
    console.print(f"  Following: {account.following_count:,}")
    console.print(f"  Verified:  {'Yes' if account.is_verified else 'No'}")
    if account.scraped_at:
        console.print(f"  Scraped:   {account.scraped_at.strftime('%Y-%m-%d %H:%M:%S')}")


# ---------------------------------------------------------------------------
# Graph stats
# ---------------------------------------------------------------------------

def print_graph_stats(account_count: int, rel_count: int, fmt: str) -> None:
    if fmt == "json":
        console.print(dump_json({"accounts": account_count, "relationships": rel_count}))
        return
    console.print(f"Accounts:      [bold]{account_count:,}[/bold]")
    console.print(f"Relationships: [bold]{rel_count:,}[/bold]")

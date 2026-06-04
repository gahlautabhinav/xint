from __future__ import annotations

import asyncio
import uuid

import click

from cli._db import setup_db
from cli.formatters.output import console, print_job_detail, print_jobs_table


@click.group()
def jobs() -> None:
    """Manage crawl jobs."""


@jobs.command("list")
@click.option("--limit", default=20, show_default=True, help="Max jobs to show")
@click.option(
    "--format",
    "fmt",
    default="table",
    show_default=True,
    type=click.Choice(["table", "json"]),
)
def jobs_list(limit: int, fmt: str) -> None:
    """List recent crawl jobs."""
    asyncio.run(_list_jobs(limit, fmt))


@jobs.command("show")
@click.argument("job_id")
@click.option(
    "--format",
    "fmt",
    default="table",
    show_default=True,
    type=click.Choice(["table", "json"]),
)
def jobs_show(job_id: str, fmt: str) -> None:
    """Show detail and events for a job."""
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {job_id!r}[/red]")
        raise SystemExit(1) from None
    asyncio.run(_show_job(jid, fmt))


# ---------------------------------------------------------------------------
# Async implementations
# ---------------------------------------------------------------------------


async def _list_jobs(limit: int, fmt: str) -> None:
    from storage.repositories.job_repo import JobRepository

    engine, factory = await setup_db()
    try:
        async with factory() as session:
            repo = JobRepository(session)
            job_list = await repo.list_jobs(limit=limit)
        print_jobs_table(job_list, fmt)
    finally:
        await engine.dispose()


async def _show_job(job_id: uuid.UUID, fmt: str) -> None:
    from storage.repositories.job_repo import JobRepository

    engine, factory = await setup_db()
    try:
        async with factory() as session:
            repo = JobRepository(session)
            job = await repo.get_job(job_id)
            if job is None:
                console.print(f"[red]Job {job_id} not found.[/red]")
                raise SystemExit(1)
            events = await repo.get_events_since(job_id, since_sequence=0)
        print_job_detail(job, events, fmt)
    finally:
        await engine.dispose()

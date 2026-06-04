from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from cli._db import setup_db

console = Console()
logger = logging.getLogger(__name__)


@click.command()
@click.argument("username")
@click.option("--depth", "-d", default=None, type=int, help="BFS depth (default: settings.DEFAULT_DEPTH)")
@click.option("--max-accounts", "-n", default=None, type=int, help="Account cap (default: settings.DEFAULT_MAX_ACCOUNTS)")
@click.option(
    "--rate-profile",
    "-r",
    default=None,
    type=click.Choice(["conservative", "moderate", "aggressive"]),
    help="Rate limiting profile",
)
@click.option("--proxy-file", "-p", default=None, type=click.Path(), help="Path to proxies.txt")
def crawl(
    username: str,
    depth: int | None,
    max_accounts: int | None,
    rate_profile: str | None,
    proxy_file: str | None,
) -> None:
    """Crawl @USERNAME and build the OSINT graph."""
    asyncio.run(_do_crawl(username, depth, max_accounts, rate_profile, proxy_file))


async def _do_crawl(
    username: str,
    depth: int | None,
    max_accounts: int | None,
    rate_profile: str | None,
    proxy_file: str | None,
) -> None:
    from config.settings import get_settings
    from graph.backends.networkx_backend import NetworkxBackend
    from scraper.jobs.crawler import AccountCrawler, CrawlerConfig
    from scraper.proxy.loader import load_from_file
    from scraper.session import authed_browser_config, has_twitter_session
    from storage.models.job import CrawlJob, JobStatus
    from storage.repositories.job_repo import JobRepository

    settings = get_settings()

    proxy_urls: list[str] = []
    source = proxy_file or settings.PROXY_FILE
    if Path(source).exists():
        proxies = load_from_file(source)
        proxy_urls = [p.url for p in proxies]
        if proxy_urls:
            console.print(f"[dim]Loaded {len(proxy_urls)} proxies from {source}[/dim]")

    engine, factory = await setup_db()
    graph_backend = NetworkxBackend()

    resolved_depth = depth or settings.DEFAULT_DEPTH
    resolved_max = max_accounts or settings.DEFAULT_MAX_ACCOUNTS
    resolved_rate = rate_profile or settings.RATE_PROFILE

    config = CrawlerConfig(
        seed_username=username,
        max_depth=resolved_depth,
        max_accounts=resolved_max,
        rate_profile_name=resolved_rate,  # type: ignore[arg-type]
        proxy_urls=proxy_urls,
    )

    console.print(
        f"[bold]Crawling @{username}[/bold]  "
        f"depth={resolved_depth}  max={resolved_max}  rate={resolved_rate}"
    )
    if not has_twitter_session():
        console.print(
            "[yellow]No saved X session — anonymous scraping returns little data. "
            "Run `xint login` first.[/yellow]"
        )

    crawler = AccountCrawler(config, factory, graph_backend, browser_config=authed_browser_config())

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
        console=console,
    ) as progress:
        prog_task = progress.add_task("Scraping accounts…", total=resolved_max)
        crawl_task: asyncio.Task[object] = asyncio.create_task(crawler.run())

        job_id = None
        while not crawl_task.done():
            await asyncio.sleep(2)

            if job_id is None:
                from sqlalchemy import select

                from storage.models.job import CrawlJob as CJModel

                async with factory() as session:
                    stmt = (
                        select(CJModel)
                        .where(CJModel.status == JobStatus.RUNNING)
                        .order_by(CJModel.created_at.desc())
                        .limit(1)
                    )
                    result = await session.execute(stmt)
                    running = result.scalar_one_or_none()
                    if running:
                        job_id = running.id

            if job_id is not None:
                async with factory() as session:
                    repo = JobRepository(session)
                    job = await repo.get_job(job_id)
                    if job is not None:
                        progress.update(
                            prog_task,
                            completed=job.accounts_scraped,
                            description=f"Scraped {job.accounts_scraped} accounts…",
                        )

        final_job_id = await crawl_task

    # Final summary
    final_job: CrawlJob | None = None
    if final_job_id is not None:
        async with factory() as session:
            repo = JobRepository(session)
            final_job = await repo.get_job(final_job_id)  # type: ignore[arg-type]

    await engine.dispose()

    if final_job is None:
        console.print("[red]Crawl failed: no job record found[/red]")
        return

    color = "green" if final_job.status == JobStatus.COMPLETED else "red"
    console.print(f"\n[{color}]Crawl {final_job.status.value}[/{color}]")
    console.print(f"Accounts scraped: [bold]{final_job.accounts_scraped}[/bold]")
    if final_job.error_message:
        console.print(f"[red]Error: {final_job.error_message}[/red]")

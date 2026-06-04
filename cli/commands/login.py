from __future__ import annotations

import asyncio

import click

from cli.formatters.output import console


@click.command()
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Run the login browser headless (not recommended — you can't see the form).",
)
def login(headless: bool) -> None:
    """Log in to X/Twitter once and save the session for authenticated crawling."""
    from scraper.auth import save_login_session

    console.print("[bold]Opening a browser for X/Twitter login…[/bold]")
    try:
        path = asyncio.run(save_login_session(headless=headless))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Login failed:[/red] {exc}")
        raise SystemExit(1) from exc

    console.print(f"[green]✓ Session saved →[/green] {path}")
    console.print(
        "[dim]Crawls will now run authenticated. Re-run `xint login` if the session expires.[/dim]"
    )

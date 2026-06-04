from __future__ import annotations

import asyncio

import click

from cli.formatters.output import console

_COOKIE_HELP = """\
[bold]Import your X session cookies[/bold] (most reliable — X blocks automated logins):

  1. Open [bold]x.com[/bold] in a browser where you're already logged in.
  2. Open DevTools (F12) → [bold]Application[/bold] tab → Storage → [bold]Cookies[/bold] → https://x.com
  3. Copy the values of the [bold]auth_token[/bold] and [bold]ct0[/bold] cookies.
"""


@click.command()
@click.option(
    "--cookies",
    "use_cookies",
    is_flag=True,
    default=False,
    help="Import auth_token + ct0 cookies instead of automating a browser login (recommended).",
)
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Run the login browser headless (not recommended — you can't see the form).",
)
def login(use_cookies: bool, headless: bool) -> None:
    """Save an X/Twitter session for authenticated crawling.

    \b
    Two methods:
      xint login              # opens a browser to log in (X may rate-limit this)
      xint login --cookies    # paste auth_token + ct0 cookies (most reliable)
    """
    if use_cookies:
        _login_with_cookies()
        return

    from scraper.auth import save_login_session

    console.print("[bold]Opening a browser for X/Twitter login…[/bold]")
    console.print(
        "[dim]If X says “we've temporarily limited your login”, "
        "re-run with [bold]--cookies[/bold] instead.[/dim]"
    )
    try:
        path = asyncio.run(save_login_session(headless=headless))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Login failed:[/red] {exc}")
        raise SystemExit(1) from exc

    console.print(f"[green]✓ Session saved →[/green] {path}")
    console.print(
        "[dim]Crawls will now run authenticated. Re-run `xint login` if the session expires.[/dim]"
    )


def _login_with_cookies() -> None:
    from scraper.auth import save_session_from_cookies

    console.print(_COOKIE_HELP)
    auth_token = click.prompt("auth_token", hide_input=True).strip()
    ct0 = click.prompt("ct0", hide_input=True).strip()

    try:
        path = save_session_from_cookies(auth_token, ct0)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc

    console.print(f"[green]✓ Session saved →[/green] {path}")
    console.print(
        "[dim]Crawls will now run authenticated. Cookies expire eventually — "
        "re-import if scraping starts returning nothing.[/dim]"
    )

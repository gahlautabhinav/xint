from __future__ import annotations

import json
from pathlib import Path

import click

from cli.formatters.output import console


@click.group()
def auth() -> None:
	"""Manage authentication and sessions."""


@auth.command()
def revoke() -> None:
	"""Delete the saved X/Twitter session (log out).

	\b
	After revoking, run 'xint login' or 'xint login --cookies' to log in
	with a different account.
	"""
	session_path = Path("config/sessions/twitter_state.json")

	if not session_path.exists():
		console.print("[dim]No session to revoke.[/dim]")
		return

	try:
		session_path.unlink()
		console.print("[green]Session revoked[/green]")
		console.print("[dim]Run [bold]xint login[/bold] to log in with a different account.[/dim]")
	except OSError as exc:
		console.print(f"[red]Failed to delete session:[/red] {exc}")
		raise SystemExit(1) from exc


@auth.command()
def status() -> None:
	"""Check if you're logged in with a saved X/Twitter session."""
	session_path = Path("config/sessions/twitter_state.json")

	if not session_path.exists():
		console.print("[yellow]NOT LOGGED IN[/yellow]")
		console.print("[dim]Run [bold]xint login[/bold] or [bold]xint login --cookies[/bold] to authenticate.[/dim]")
		raise SystemExit(1)

	try:
		with open(session_path) as f:
			data = json.load(f)
	except (json.JSONDecodeError, OSError) as exc:
		console.print(f"[red]SESSION CORRUPTED:[/red] {exc}")
		console.print("[dim]Re-run [bold]xint login[/bold] to fix.[/dim]")
		raise SystemExit(1) from exc

	# Try to extract account info from cookies
	cookies = data.get("cookies", [])
	auth_token = next((c.get("value") for c in cookies if c.get("name") == "auth_token"), None)

	if auth_token:
		console.print("[green]LOGGED IN[/green]")
		console.print(f"[dim]Session file: {session_path}[/dim]")
		console.print(f"[dim]Token (first 20 chars): {auth_token[:20]}...[/dim]")
	else:
		console.print("[yellow]SESSION FOUND BUT NO AUTH TOKEN[/yellow]")
		console.print("[dim]Run [bold]xint login --cookies[/bold] to re-import.[/dim]")

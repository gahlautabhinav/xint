from __future__ import annotations

import asyncio

import click

from cli._db import setup_db
from cli.formatters.output import console, print_account_detail, print_accounts_table


@click.group()
def accounts() -> None:
    """Browse scraped accounts."""


@accounts.command("list")
@click.option("--query", "-q", default=None, help="Substring search (username / bio)")
@click.option("--limit", default=20, show_default=True)
@click.option(
    "--format",
    "fmt",
    default="table",
    show_default=True,
    type=click.Choice(["table", "json"]),
)
def accounts_list(query: str | None, limit: int, fmt: str) -> None:
    """List scraped accounts."""
    asyncio.run(_list_accounts(query, limit, fmt))


@accounts.command("show")
@click.argument("handle")
@click.option("--platform", default="twitter", show_default=True)
@click.option(
    "--format",
    "fmt",
    default="table",
    show_default=True,
    type=click.Choice(["table", "json"]),
)
def accounts_show(handle: str, platform: str, fmt: str) -> None:
    """Show detail for a single account."""
    asyncio.run(_show_account(handle.lstrip("@"), platform, fmt))


# ---------------------------------------------------------------------------
# Async implementations
# ---------------------------------------------------------------------------


async def _list_accounts(query: str | None, limit: int, fmt: str) -> None:
    from sqlalchemy import select

    from storage.models.account import Account
    from storage.repositories.account_repo import AccountRepository

    engine, factory = await setup_db()
    try:
        async with factory() as session:
            repo = AccountRepository(session)
            if query:
                account_list = await repo.search(query, limit=limit)
            else:
                stmt = (
                    select(Account)
                    .order_by(Account.scraped_at.desc().nulls_last())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                account_list = list(result.scalars().all())
        print_accounts_table(account_list, fmt)
    finally:
        await engine.dispose()


async def _show_account(handle: str, platform: str, fmt: str) -> None:
    from storage.repositories.account_repo import AccountRepository

    engine, factory = await setup_db()
    try:
        async with factory() as session:
            repo = AccountRepository(session)
            account = await repo.get_by_username(handle, platform=platform)
        if account is None:
            console.print(f"[red]Account {platform}/@{handle} not found.[/red]")
            raise SystemExit(1)
        print_account_detail(account, fmt)
    finally:
        await engine.dispose()

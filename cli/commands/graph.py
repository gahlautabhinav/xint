from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from cli._db import setup_db
from cli.formatters.output import console, dump_json, print_graph_stats


@click.group()
def graph() -> None:
    """Explore the relationship graph."""


@graph.command("stats")
@click.option(
    "--format",
    "fmt",
    default="table",
    show_default=True,
    type=click.Choice(["table", "json"]),
)
def graph_stats(fmt: str) -> None:
    """Show total account and relationship counts."""
    asyncio.run(_show_stats(fmt))


@graph.command("export")
@click.argument("handle")
@click.option("--platform", default="twitter", show_default=True)
@click.option("--depth", default=2, show_default=True, type=int, help="BFS depth")
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(),
    help="Output file path (default: stdout)",
)
def graph_export(handle: str, platform: str, depth: int, output: str | None) -> None:
    """Export a subgraph rooted at HANDLE to JSON.

    Builds the subgraph from the relational database so no in-memory
    graph session needs to be running.
    """
    asyncio.run(_export_graph(handle.lstrip("@"), platform, depth, output))


# ---------------------------------------------------------------------------
# Async implementations
# ---------------------------------------------------------------------------


async def _show_stats(fmt: str) -> None:
    from storage.repositories.account_repo import AccountRepository
    from storage.repositories.relationship_repo import RelationshipRepository

    engine, factory = await setup_db()
    try:
        async with factory() as session:
            a_repo = AccountRepository(session)
            r_repo = RelationshipRepository(session)
            account_count = await a_repo.count()
            rel_count = await r_repo.count()
        print_graph_stats(account_count, rel_count, fmt)
    finally:
        await engine.dispose()


async def _export_graph(
    handle: str,
    platform: str,
    depth: int,
    output: str | None,
) -> None:
    """Build a BFS subgraph from the relational DB and export as JSON."""

    from storage.models.account import Account
    from storage.models.relationship import Relationship
    from storage.repositories.account_repo import AccountRepository
    from storage.repositories.relationship_repo import RelationshipRepository

    engine, factory = await setup_db()
    try:
        async with factory() as session:
            a_repo = AccountRepository(session)
            root = await a_repo.get_by_username(handle, platform=platform)
            if root is None:
                console.print(f"[red]Account {platform}/@{handle} not found in database.[/red]")
                raise SystemExit(1)

            # BFS over relational edges
            visited_ids: set[object] = set()
            frontier = [root]
            all_accounts: dict[object, Account] = {root.id: root}
            all_rels: list[Relationship] = []

            for _ in range(depth):
                if not frontier:
                    break
                next_frontier = []
                for acct in frontier:
                    if acct.id in visited_ids:
                        continue
                    visited_ids.add(acct.id)
                    r_repo = RelationshipRepository(session)
                    rels = await r_repo.get_by_account(acct.id, direction="outgoing")
                    for rel in rels:
                        all_rels.append(rel)
                        if rel.target_account_id not in all_accounts:
                            target = await a_repo.get_by_id(rel.target_account_id)
                            if target is not None:
                                all_accounts[target.id] = target
                                next_frontier.append(target)
                frontier = next_frontier

        nodes = [
            {
                "id": str(a.id),
                "username": a.username,
                "platform": a.platform,
                "display_name": a.display_name,
                "followers_count": a.followers_count,
                "is_verified": a.is_verified,
            }
            for a in all_accounts.values()
        ]
        edges = [
            {
                "source": str(r.source_account_id),
                "target": str(r.target_account_id),
                "rel_type": r.rel_type.value,
                "weight": r.weight,
                "evidence_count": r.evidence_count,
            }
            for r in all_rels
        ]
        payload = {"nodes": nodes, "edges": edges}
        text = dump_json(payload)

        if output:
            Path(output).write_text(text, encoding="utf-8")
            console.print(
                f"Exported [bold]{len(nodes)}[/bold] nodes and "
                f"[bold]{len(edges)}[/bold] edges to [bold]{output}[/bold]"
            )
        else:
            sys.stdout.write(text + "\n")
    finally:
        await engine.dispose()

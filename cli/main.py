from __future__ import annotations

import click

from cli.commands.accounts import accounts
from cli.commands.crawl import crawl
from cli.commands.graph import graph
from cli.commands.jobs import jobs
from cli.commands.login import login


@click.group()
@click.version_option(version="0.1.0", prog_name="xint")
def cli() -> None:
    """xint — Twitter/X OSINT network mapper.

    \b
    Quick start:
      xint login                       # authenticate once (X needs a session)
      xint crawl elonmusk --depth 2 --max-accounts 200
      xint jobs list
      xint accounts list
      xint graph export elonmusk -o graph.json
    """


cli.add_command(login)
cli.add_command(crawl)
cli.add_command(jobs)
cli.add_command(accounts)
cli.add_command(graph)

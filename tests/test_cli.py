from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.main import cli

# ---------------------------------------------------------------------------
# Helpers — build mock ORM objects
# ---------------------------------------------------------------------------


def _mock_job(
    seed: str = "alice",
    status: str = "COMPLETED",
    scraped: int = 5,
    job_id: uuid.UUID | None = None,
) -> MagicMock:
    j = MagicMock()
    j.id = job_id or uuid.uuid4()
    j.seed_username = seed
    j.platform = "twitter"
    j.status = MagicMock()
    j.status.value = status
    j.max_depth = 2
    j.max_accounts = 100
    j.accounts_scraped = scraped
    j.error_message = None
    j.created_at = datetime.now(timezone.utc)
    j.started_at = datetime.now(timezone.utc)
    j.completed_at = datetime.now(timezone.utc)
    j.updated_at = None
    return j


def _mock_account(
    username: str = "alice",
    platform: str = "twitter",
    followers: int = 100,
) -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.username = username
    a.platform = platform
    a.display_name = f"Display {username}"
    a.bio = "test bio"
    a.website = None
    a.followers_count = followers
    a.following_count = 50
    a.is_verified = False
    a.scraped_at = datetime.now(timezone.utc)
    a.scrape_depth = 1
    return a


def _mock_event(seq: int = 1, event_type: str = "account_scraped") -> MagicMock:
    e = MagicMock()
    e.id = uuid.uuid4()
    e.job_id = uuid.uuid4()
    e.sequence = seq
    e.event_type = event_type
    e.payload = {"username": "bob"}
    e.created_at = datetime.now(timezone.utc)
    return e


# ---------------------------------------------------------------------------
# Fixture: CliRunner
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Help / version
# ---------------------------------------------------------------------------


def test_help(runner: CliRunner) -> None:
    r = runner.invoke(cli, ["--help"])
    assert r.exit_code == 0
    assert "crawl" in r.output
    assert "jobs" in r.output
    assert "accounts" in r.output
    assert "graph" in r.output


def test_version(runner: CliRunner) -> None:
    r = runner.invoke(cli, ["--version"])
    assert r.exit_code == 0
    assert "0.1.0" in r.output


# ---------------------------------------------------------------------------
# xint crawl
# ---------------------------------------------------------------------------


def test_crawl_help(runner: CliRunner) -> None:
    r = runner.invoke(cli, ["crawl", "--help"])
    assert r.exit_code == 0
    assert "USERNAME" in r.output


def test_crawl_invokes_crawler(runner: CliRunner) -> None:
    async def fake_do_crawl(*args, **kwargs):  # noqa: ARG001
        pass

    with patch("cli.commands.crawl._do_crawl", side_effect=fake_do_crawl):
        r = runner.invoke(cli, ["crawl", "testuser"])

    assert r.exit_code == 0


def test_crawl_options(runner: CliRunner) -> None:
    captured: dict = {}

    async def fake_do_crawl(username, depth, max_accounts, rate_profile, proxy_file):
        captured.update(
            username=username,
            depth=depth,
            max_accounts=max_accounts,
            rate_profile=rate_profile,
            proxy_file=proxy_file,
        )

    with patch("cli.commands.crawl._do_crawl", side_effect=fake_do_crawl):
        r = runner.invoke(
            cli,
            ["crawl", "elonmusk", "--depth", "3", "--max-accounts", "100", "--rate-profile", "conservative"],
        )

    assert r.exit_code == 0
    assert captured["username"] == "elonmusk"
    assert captured["depth"] == 3
    assert captured["max_accounts"] == 100
    assert captured["rate_profile"] == "conservative"


def test_crawl_invalid_rate_profile(runner: CliRunner) -> None:
    r = runner.invoke(cli, ["crawl", "x", "--rate-profile", "turbo"])
    assert r.exit_code != 0


# ---------------------------------------------------------------------------
# xint jobs list
# ---------------------------------------------------------------------------


def test_jobs_list_table(runner: CliRunner) -> None:
    jobs = [_mock_job(seed="alice"), _mock_job(seed="bob", status="RUNNING")]

    async def fake_list(limit, fmt):
        from cli.formatters.output import print_jobs_table
        print_jobs_table(jobs, fmt)

    with patch("cli.commands.jobs._list_jobs", side_effect=fake_list):
        r = runner.invoke(cli, ["jobs", "list"])

    assert r.exit_code == 0
    assert "alice" in r.output
    assert "bob" in r.output


def test_jobs_list_json(runner: CliRunner) -> None:
    jobs = [_mock_job(seed="alice")]

    async def fake_list(limit, fmt):
        from cli.formatters.output import print_jobs_table
        print_jobs_table(jobs, fmt)

    with patch("cli.commands.jobs._list_jobs", side_effect=fake_list):
        r = runner.invoke(cli, ["jobs", "list", "--format", "json"])

    assert r.exit_code == 0
    data = json.loads(r.output.strip())
    assert data[0]["seed_username"] == "alice"


def test_jobs_list_empty(runner: CliRunner) -> None:
    async def fake_list(limit, fmt):
        from cli.formatters.output import print_jobs_table
        print_jobs_table([], fmt)

    with patch("cli.commands.jobs._list_jobs", side_effect=fake_list):
        r = runner.invoke(cli, ["jobs", "list"])

    assert r.exit_code == 0
    assert "No jobs" in r.output


# ---------------------------------------------------------------------------
# xint jobs show
# ---------------------------------------------------------------------------


def test_jobs_show_table(runner: CliRunner) -> None:
    job = _mock_job()
    events = [_mock_event(1, "job_started"), _mock_event(2, "account_scraped")]
    jid = str(job.id)

    async def fake_show(job_id, fmt):
        from cli.formatters.output import print_job_detail
        print_job_detail(job, events, fmt)

    with patch("cli.commands.jobs._show_job", side_effect=fake_show):
        r = runner.invoke(cli, ["jobs", "show", jid])

    assert r.exit_code == 0
    assert "job_started" in r.output or "account_scraped" in r.output


def test_jobs_show_invalid_uuid(runner: CliRunner) -> None:
    r = runner.invoke(cli, ["jobs", "show", "not-a-uuid"])
    assert r.exit_code != 0


def test_jobs_show_json(runner: CliRunner) -> None:
    job = _mock_job()
    jid = str(job.id)

    async def fake_show(job_id, fmt):
        from cli.formatters.output import print_job_detail
        print_job_detail(job, [], fmt)

    with patch("cli.commands.jobs._show_job", side_effect=fake_show):
        r = runner.invoke(cli, ["jobs", "show", jid, "--format", "json"])

    assert r.exit_code == 0
    data = json.loads(r.output.strip())
    assert data["seed_username"] == job.seed_username


# ---------------------------------------------------------------------------
# xint accounts list
# ---------------------------------------------------------------------------


def test_accounts_list_table(runner: CliRunner) -> None:
    accts = [_mock_account("alice"), _mock_account("bob")]

    async def fake_list(query, limit, fmt):
        from cli.formatters.output import print_accounts_table
        print_accounts_table(accts, fmt)

    with patch("cli.commands.accounts._list_accounts", side_effect=fake_list):
        r = runner.invoke(cli, ["accounts", "list"])

    assert r.exit_code == 0
    assert "alice" in r.output
    assert "bob" in r.output


def test_accounts_list_json(runner: CliRunner) -> None:
    accts = [_mock_account("alice")]

    async def fake_list(query, limit, fmt):
        from cli.formatters.output import print_accounts_table
        print_accounts_table(accts, fmt)

    with patch("cli.commands.accounts._list_accounts", side_effect=fake_list):
        r = runner.invoke(cli, ["accounts", "list", "--format", "json"])

    assert r.exit_code == 0
    data = json.loads(r.output.strip())
    assert data[0]["username"] == "alice"


def test_accounts_list_empty(runner: CliRunner) -> None:
    async def fake_list(query, limit, fmt):
        from cli.formatters.output import print_accounts_table
        print_accounts_table([], fmt)

    with patch("cli.commands.accounts._list_accounts", side_effect=fake_list):
        r = runner.invoke(cli, ["accounts", "list"])

    assert r.exit_code == 0
    assert "No accounts" in r.output


def test_accounts_list_query_passed(runner: CliRunner) -> None:
    captured: dict = {}

    async def fake_list(query, limit, fmt):
        captured["query"] = query

    with patch("cli.commands.accounts._list_accounts", side_effect=fake_list):
        runner.invoke(cli, ["accounts", "list", "--query", "elon"])

    assert captured["query"] == "elon"


# ---------------------------------------------------------------------------
# xint accounts show
# ---------------------------------------------------------------------------


def test_accounts_show_table(runner: CliRunner) -> None:
    acct = _mock_account("alice")

    async def fake_show(handle, platform, fmt):
        from cli.formatters.output import print_account_detail
        print_account_detail(acct, fmt)

    with patch("cli.commands.accounts._show_account", side_effect=fake_show):
        r = runner.invoke(cli, ["accounts", "show", "alice"])

    assert r.exit_code == 0
    assert "alice" in r.output


def test_accounts_show_strips_at(runner: CliRunner) -> None:
    captured: dict = {}

    async def fake_show(handle, platform, fmt):
        captured["handle"] = handle

    with patch("cli.commands.accounts._show_account", side_effect=fake_show):
        runner.invoke(cli, ["accounts", "show", "@alice"])

    assert captured["handle"] == "alice"


def test_accounts_show_json(runner: CliRunner) -> None:
    acct = _mock_account("alice")

    async def fake_show(handle, platform, fmt):
        from cli.formatters.output import print_account_detail
        print_account_detail(acct, fmt)

    with patch("cli.commands.accounts._show_account", side_effect=fake_show):
        r = runner.invoke(cli, ["accounts", "show", "alice", "--format", "json"])

    assert r.exit_code == 0
    data = json.loads(r.output.strip())
    assert data["username"] == "alice"


# ---------------------------------------------------------------------------
# xint graph stats
# ---------------------------------------------------------------------------


def test_graph_stats_table(runner: CliRunner) -> None:
    async def fake_stats(fmt):
        from cli.formatters.output import print_graph_stats
        print_graph_stats(42, 150, fmt)

    with patch("cli.commands.graph._show_stats", side_effect=fake_stats):
        r = runner.invoke(cli, ["graph", "stats"])

    assert r.exit_code == 0
    assert "42" in r.output
    assert "150" in r.output


def test_graph_stats_json(runner: CliRunner) -> None:
    async def fake_stats(fmt):
        from cli.formatters.output import print_graph_stats
        print_graph_stats(42, 150, fmt)

    with patch("cli.commands.graph._show_stats", side_effect=fake_stats):
        r = runner.invoke(cli, ["graph", "stats", "--format", "json"])

    assert r.exit_code == 0
    data = json.loads(r.output.strip())
    assert data["accounts"] == 42
    assert data["relationships"] == 150


# ---------------------------------------------------------------------------
# xint graph export
# ---------------------------------------------------------------------------


def test_graph_export_stdout(runner: CliRunner) -> None:
    sample = {"nodes": [{"id": "x", "username": "alice"}], "edges": []}

    async def fake_export(handle, platform, depth, output):
        import sys

        from cli.formatters.output import dump_json
        sys.stdout.write(dump_json(sample) + "\n")

    with patch("cli.commands.graph._export_graph", side_effect=fake_export):
        r = runner.invoke(cli, ["graph", "export", "alice"])

    assert r.exit_code == 0
    data = json.loads(r.output.strip())
    assert len(data["nodes"]) == 1


def test_graph_export_file(runner: CliRunner, tmp_path) -> None:
    out_file = str(tmp_path / "graph.json")
    captured: dict = {}

    async def fake_export(handle, platform, depth, output):
        captured["output"] = output

    with patch("cli.commands.graph._export_graph", side_effect=fake_export):
        r = runner.invoke(cli, ["graph", "export", "alice", "--output", out_file])

    assert r.exit_code == 0
    assert captured["output"] == out_file


def test_graph_export_depth_option(runner: CliRunner) -> None:
    captured: dict = {}

    async def fake_export(handle, platform, depth, output):
        captured["depth"] = depth

    with patch("cli.commands.graph._export_graph", side_effect=fake_export):
        runner.invoke(cli, ["graph", "export", "alice", "--depth", "3"])

    assert captured["depth"] == 3


# ---------------------------------------------------------------------------
# xint login
# ---------------------------------------------------------------------------


def test_login_help(runner: CliRunner) -> None:
    r = runner.invoke(cli, ["login", "--help"])
    assert r.exit_code == 0
    assert "session" in r.output.lower()


def test_login_saves_session(runner: CliRunner, tmp_path) -> None:
    captured: dict = {}
    fake_path = tmp_path / "twitter_state.json"

    async def fake_save(headless: bool = False):
        captured["headless"] = headless
        return fake_path

    with patch("scraper.auth.save_login_session", side_effect=fake_save):
        r = runner.invoke(cli, ["login"])

    assert r.exit_code == 0
    assert "Session saved" in r.output
    assert captured["headless"] is False


def test_login_cookies_mode(runner: CliRunner, tmp_path) -> None:
    captured: dict = {}
    fake_path = tmp_path / "twitter_state.json"

    def fake_from_cookies(auth_token, ct0):
        captured["auth_token"] = auth_token
        captured["ct0"] = ct0
        return fake_path

    with patch("scraper.auth.save_session_from_cookies", side_effect=fake_from_cookies):
        r = runner.invoke(cli, ["login", "--cookies"], input="tok123\ncsrf456\n")

    assert r.exit_code == 0
    assert "Session saved" in r.output
    assert captured["auth_token"] == "tok123"
    assert captured["ct0"] == "csrf456"

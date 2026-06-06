"""Registry of sites checked during username enumeration.

Each :class:`Site` says how to probe ``https://…/<username>`` and how to read
the response. Detection strategy per site:

* ``"status"``  — exists iff the response status is 200; a 404 means "no such
  user". Anything else (403/429/5xx) is reported as *unknown* (the site blocked
  us or errored — we don't guess).
* ``"absent"``  — the site returns 200 even for missing users, but a "not found"
  page contains a tell-tale ``marker`` string. Exists iff that marker is absent.
* ``"present"`` — the opposite: a real profile page contains ``marker``.

Sites that only render via JavaScript, hard-block datacenter IPs, or *soft-404*
(return HTTP 200 with a "not found" page for missing users) are omitted on
purpose — a false *found* misleads an analyst, so a confident *not_found* or an
honest *unknown* is worth far more than a flaky guess. Verified empirically:
Instagram, Pinterest, Reddit, Replit and PyPI all soft-404 and were dropped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    name: str
    category: str
    url: str                     # ``.format(username=…)`` target
    check: str = "status"        # "status" | "absent" | "present"
    marker: str | None = None    # substring for absent/present checks


# Curated for reliable signal from a plain HTTP client (no browser). Leans on
# 404-detection; a couple of message-marker sites exercise that path too.
SITES: list[Site] = [
    # ── Code / dev ──────────────────────────────────────────────────────────
    Site("GitHub", "code", "https://github.com/{username}"),
    Site("GitLab", "code", "https://gitlab.com/{username}"),
    Site("Keybase", "code", "https://keybase.io/{username}"),
    Site("npm", "code", "https://www.npmjs.com/~{username}"),
    Site(
        "HackerNews", "code",
        "https://news.ycombinator.com/user?id={username}",
        check="absent", marker="No such user.",
    ),
    # ── Social ──────────────────────────────────────────────────────────────
    Site("TikTok", "social", "https://www.tiktok.com/@{username}"),
    Site("Mastodon", "social", "https://mastodon.social/@{username}"),
    Site("Linktree", "social", "https://linktr.ee/{username}"),
    Site("About.me", "social", "https://about.me/{username}"),
    Site("ProductHunt", "social", "https://www.producthunt.com/@{username}"),
    # ── Media / creative ────────────────────────────────────────────────────
    Site("YouTube", "media", "https://www.youtube.com/@{username}"),
    Site("SoundCloud", "media", "https://soundcloud.com/{username}"),
    Site("Vimeo", "media", "https://vimeo.com/{username}"),
    Site("Behance", "media", "https://www.behance.net/{username}"),
    Site("Dribbble", "media", "https://dribbble.com/{username}"),
    Site("Flickr", "media", "https://www.flickr.com/people/{username}"),
    Site("DeviantArt", "media", "https://www.deviantart.com/{username}"),
    Site("VSCO", "media", "https://vsco.co/{username}"),
    # ── Blog / writing ──────────────────────────────────────────────────────
    Site("Medium", "blog", "https://medium.com/@{username}"),
    Site("Dev.to", "blog", "https://dev.to/{username}"),
    Site("Tumblr", "blog", "https://{username}.tumblr.com"),
    # ── Gaming ──────────────────────────────────────────────────────────────
    Site(
        "Steam", "gaming",
        "https://steamcommunity.com/id/{username}",
        check="absent", marker="The specified profile could not be found.",
    ),
    Site("Chess.com", "gaming", "https://www.chess.com/member/{username}"),
    Site("Lichess", "gaming", "https://lichess.org/@/{username}"),
    # ── Other ───────────────────────────────────────────────────────────────
    Site("Last.fm", "other", "https://www.last.fm/user/{username}"),
    Site("Letterboxd", "other", "https://letterboxd.com/{username}/"),
    Site("Gravatar", "other", "https://gravatar.com/{username}"),
    Site("Patreon", "other", "https://www.patreon.com/{username}"),
]

from __future__ import annotations

# ---------------------------------------------------------------------------
# Edge (relationship) type constants
# ---------------------------------------------------------------------------

FOLLOWS: str = "FOLLOWS"
"""Account A follows account B on the same platform."""

MENTIONS: str = "MENTIONS"
"""Account A mentions @B in a tweet/post body."""

REPLIES_TO: str = "REPLIES_TO"
"""Account A posts a direct reply to a tweet authored by account B."""

QUOTE_TWEETS: str = "QUOTE_TWEETS"
"""Account A quote-tweets a tweet authored by account B."""

RETWEETS: str = "RETWEETS"
"""Account A reposts (retweets) a tweet authored by account B."""

CROSS_PLATFORM_LINK: str = "CROSS_PLATFORM_LINK"
"""Account A's profile (bio / pinned tweet / website field) contains a
discoverable link to account B on a *different* platform."""

# ---------------------------------------------------------------------------
# Convenience collection — use for validation and filtering
# ---------------------------------------------------------------------------

ALL_REL_TYPES: list[str] = [
    FOLLOWS,
    MENTIONS,
    REPLIES_TO,
    QUOTE_TWEETS,
    RETWEETS,
    CROSS_PLATFORM_LINK,
]

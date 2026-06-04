from __future__ import annotations

# ---------------------------------------------------------------------------
# Node label constants
# ---------------------------------------------------------------------------

ACCOUNT = "Account"

# Ordered list of all node labels — extend here as new types are added.
PLATFORM_NODES: list[str] = [ACCOUNT]


# ---------------------------------------------------------------------------
# node_id helpers
# ---------------------------------------------------------------------------

def make_node_id(platform: str, handle: str) -> str:
    """Return the canonical node_id for a given platform and handle.

    The node_id format is ``"<platform>:<@handle>"``, all lower-case.
    A leading ``@`` is inserted when missing.

    Examples::

        >>> make_node_id("twitter", "elonmusk")
        'twitter:@elonmusk'
        >>> make_node_id("GitHub", "@Torvalds")
        'github:@torvalds'
    """
    handle = handle if handle.startswith("@") else f"@{handle}"
    return f"{platform.lower()}:{handle.lower()}"


def parse_node_id(node_id: str) -> tuple[str, str]:
    """Split a node_id into ``(platform, handle)``.

    Raises :class:`ValueError` when the string is not in the expected
    ``"platform:@handle"`` format.

    Examples::

        >>> parse_node_id("twitter:@elonmusk")
        ('twitter', '@elonmusk')
    """
    if ":" not in node_id:
        raise ValueError(
            f"Invalid node_id {node_id!r}: expected format 'platform:@handle'"
        )
    platform, handle = node_id.split(":", 1)
    if not platform:
        raise ValueError(f"Invalid node_id {node_id!r}: platform part is empty")
    if not handle:
        raise ValueError(f"Invalid node_id {node_id!r}: handle part is empty")
    return platform, handle

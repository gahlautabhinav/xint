from __future__ import annotations

from unittest.mock import AsyncMock, patch

from scraper.extractors.cross_platform import extract_all_links, extract_cross_platform_links
from scraper.extractors.twitter import (
    ProfileData,
    TweetData,
    _parse_count,
    extract_following,
    extract_hashtags_from_text,
    extract_mentions_from_text,
    extract_profile,
    extract_tweets,
)

# ---------------------------------------------------------------------------
# _parse_count
# ---------------------------------------------------------------------------


class TestParseCount:
    def test_plain_integer(self):
        assert _parse_count("1234") == 1234

    def test_comma_separated(self):
        assert _parse_count("1,234") == 1234

    def test_k_suffix(self):
        assert _parse_count("12.3K") == 12_300

    def test_m_suffix(self):
        assert _parse_count("3.4M") == 3_400_000

    def test_b_suffix(self):
        assert _parse_count("1B") == 1_000_000_000

    def test_none_input(self):
        assert _parse_count(None) is None

    def test_empty_string(self):
        assert _parse_count("") is None

    def test_non_numeric_string(self):
        assert _parse_count("followers") is None

    def test_trailing_text_ignored(self):
        assert _parse_count("5.6K followers") == 5_600

    def test_lowercase_suffix(self):
        assert _parse_count("2k") == 2_000


# ---------------------------------------------------------------------------
# extract_profile
# ---------------------------------------------------------------------------


class TestExtractProfile:
    async def test_full_data_returned(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value={
                "handle": "johndoe",
                "display_name": "John Doe",
                "bio": "Developer & writer",
                "website": "https://johndoe.dev",
                "followers_raw": "12.3K",
                "following_raw": "456",
                "is_verified": True,
            }
        )
        result = await extract_profile(page)
        assert isinstance(result, ProfileData)
        assert result.handle == "johndoe"
        assert result.display_name == "John Doe"
        assert result.bio == "Developer & writer"
        assert result.website == "https://johndoe.dev"
        assert result.follower_count == 12_300
        assert result.following_count == 456
        assert result.is_verified is True

    async def test_missing_fields_are_none(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value={
                "handle": "partial",
                "display_name": None,
                "bio": None,
                "website": None,
                "followers_raw": None,
                "following_raw": None,
                "is_verified": False,
            }
        )
        result = await extract_profile(page)
        assert result.handle == "partial"
        assert result.follower_count is None
        assert result.is_verified is False

    async def test_evaluate_exception_returns_empty(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=Exception("page crashed"))
        result = await extract_profile(page)
        assert result.handle is None
        assert result.bio is None

    async def test_is_verified_false_by_default(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value={"handle": "x", "is_verified": False})
        result = await extract_profile(page)
        assert result.is_verified is False

    async def test_follower_count_large_number(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value={"followers_raw": "2.1M", "is_verified": False}
        )
        result = await extract_profile(page)
        assert result.follower_count == 2_100_000


# ---------------------------------------------------------------------------
# extract_tweets
# ---------------------------------------------------------------------------


class TestExtractTweets:
    async def test_multiple_tweets(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                {
                    "tweet_id": "111",
                    "text": "Hello @alice #python",
                    "timestamp": "2024-01-01T10:00:00.000Z",
                    "quote_url": None,
                },
                {
                    "tweet_id": "222",
                    "text": "Check out #rust",
                    "timestamp": "2024-01-02T10:00:00.000Z",
                    "quote_url": None,
                },
            ]
        )
        tweets = await extract_tweets(page)
        assert len(tweets) == 2
        assert tweets[0].tweet_id == "111"
        assert tweets[0].text == "Hello @alice #python"
        assert tweets[0].mentions == ["alice"]
        assert tweets[0].hashtags == ["python"]
        assert tweets[1].hashtags == ["rust"]

    async def test_empty_list_on_evaluate_failure(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=Exception("no page"))
        tweets = await extract_tweets(page)
        assert tweets == []

    async def test_no_tweets_returns_empty_list(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value=[])
        tweets = await extract_tweets(page)
        assert tweets == []

    async def test_tweet_data_types(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                {"tweet_id": "999", "text": "test", "timestamp": None, "quote_url": None}
            ]
        )
        tweets = await extract_tweets(page)
        assert isinstance(tweets[0], TweetData)
        assert tweets[0].timestamp is None
        assert tweets[0].mentions == []

    async def test_quote_url_preserved(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                {
                    "tweet_id": "555",
                    "text": "quoting this",
                    "timestamp": None,
                    "quote_url": "/user/status/12345",
                    "reply_to": None,
                }
            ]
        )
        tweets = await extract_tweets(page)
        assert tweets[0].quote_url == "/user/status/12345"

    async def test_reply_to_extracted(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(
            return_value=[
                {
                    "tweet_id": "777",
                    "text": "@alice great point",
                    "timestamp": None,
                    "quote_url": None,
                    "reply_to": "alice",
                }
            ]
        )
        tweets = await extract_tweets(page)
        assert tweets[0].reply_to == "alice"


# ---------------------------------------------------------------------------
# extract_mentions_from_text / extract_hashtags_from_text
# ---------------------------------------------------------------------------


class TestExtractMentionsFromText:
    def test_single_mention(self):
        assert extract_mentions_from_text("Hello @alice") == ["alice"]

    def test_multiple_mentions(self):
        result = extract_mentions_from_text("@alice and @bob are great")
        assert "alice" in result
        assert "bob" in result

    def test_no_mentions(self):
        assert extract_mentions_from_text("no mentions here") == []

    def test_mention_strip_at(self):
        result = extract_mentions_from_text("@user123")
        assert result == ["user123"]


class TestExtractHashtagsFromText:
    def test_single_hashtag(self):
        assert extract_hashtags_from_text("Love #python") == ["python"]

    def test_multiple_hashtags(self):
        result = extract_hashtags_from_text("#rust #go #python")
        assert result == ["rust", "go", "python"]

    def test_no_hashtags(self):
        assert extract_hashtags_from_text("plain text") == []


# ---------------------------------------------------------------------------
# extract_cross_platform_links
# ---------------------------------------------------------------------------


class TestExtractCrossPlatformLinks:
    def test_instagram_full_url(self):
        r = extract_cross_platform_links("Follow me at https://www.instagram.com/johndoe/")
        assert r.get("instagram") == "johndoe"

    def test_github_url(self):
        r = extract_cross_platform_links("Code: https://github.com/johndoe/myrepo")
        assert r.get("github") == "johndoe"

    def test_linkedin_url(self):
        r = extract_cross_platform_links("linkedin.com/in/john-doe")
        assert r.get("linkedin") == "john-doe"

    def test_tiktok_url(self):
        r = extract_cross_platform_links("TikTok: https://tiktok.com/@johndoe")
        assert r.get("tiktok") == "johndoe"

    def test_youtube_at_handle(self):
        r = extract_cross_platform_links("youtube.com/@mychannel")
        assert r.get("youtube") == "mychannel"

    def test_multiple_platforms_in_one_text(self):
        bio = "github.com/dev | instagram.com/dev_pics | tiktok.com/@dev_vids"
        r = extract_cross_platform_links(bio)
        assert "github" in r
        assert "instagram" in r
        assert "tiktok" in r

    def test_no_match_returns_empty(self):
        assert extract_cross_platform_links("nothing here") == {}

    def test_case_insensitive(self):
        r = extract_cross_platform_links("INSTAGRAM.COM/CapsUser")
        assert r.get("instagram") == "CapsUser"

    def test_handle_strips_trailing_slash(self):
        r = extract_cross_platform_links("instagram.com/user/")
        assert r["instagram"] == "user"


# ---------------------------------------------------------------------------
# extract_all_links
# ---------------------------------------------------------------------------


class TestExtractAllLinks:
    def test_merges_multiple_texts(self):
        texts = ["github.com/dev", "instagram.com/dev_ig"]
        r = extract_all_links(texts)
        assert r.get("github") == "dev"
        assert r.get("instagram") == "dev_ig"

    def test_first_occurrence_wins(self):
        texts = ["github.com/first", "github.com/second"]
        r = extract_all_links(texts)
        assert r["github"] == "first"

    def test_empty_list(self):
        assert extract_all_links([]) == {}

    def test_empty_strings(self):
        assert extract_all_links(["", "   "]) == {}


# ---------------------------------------------------------------------------
# extract_following (accumulate across virtualized scrolls)
# ---------------------------------------------------------------------------


class TestExtractFollowing:
    async def test_dedups_and_preserves_order(self):
        # X recycles cells on scroll; batches overlap. Result must dedupe,
        # keep first-seen order, and skip reserved handles.
        batches = [["alice", "bob", "alice"], ["bob", "home", "carol"], ["carol", "dave"]]
        idx = {"n": 0}

        async def fake_eval(js, *args, **kwargs):
            if "scrollBy" in js:
                return None
            i = min(idx["n"], len(batches) - 1)
            idx["n"] += 1
            return batches[i]

        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=fake_eval)
        with patch("scraper.extractors.twitter.asyncio.sleep", new=AsyncMock()):
            result = await extract_following(page, max_count=10, max_scrolls=10)

        assert result == ["alice", "bob", "carol", "dave"]  # "home" reserved → dropped

    async def test_respects_max_count(self):
        async def fake_eval(js, *args, **kwargs):
            if "scrollBy" in js:
                return None
            return ["a", "b", "c", "d", "e"]

        page = AsyncMock()
        page.evaluate = AsyncMock(side_effect=fake_eval)
        with patch("scraper.extractors.twitter.asyncio.sleep", new=AsyncMock()):
            result = await extract_following(page, max_count=3, max_scrolls=10)

        assert result == ["a", "b", "c"]

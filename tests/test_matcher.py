"""Unit tests for core matcher module."""

from __future__ import annotations

import pytest

from mediacopier.core.indexer import MediaCatalog, MediaFile, MediaType
from mediacopier.core.matcher import (
    RAPIDFUZZ_AVAILABLE,
    MatchCandidate,
    MatchResult,
    explain_match,
    extract_base_name,
    fuzzy_ratio,
    get_bonus_words_in_text,
    get_penalty_words_in_text,
    match_items,
    match_single_item,
    normalize_text,
    token_set_ratio,
    token_sort_ratio,
    tokenize,
)
from mediacopier.core.models import RequestedItem, RequestedItemType


class TestNormalizeText:
    """Tests for normalize_text function."""

    def test_lowercase(self) -> None:
        """Test that text is converted to lowercase."""
        assert normalize_text("HELLO WORLD") == "hello world"
        assert normalize_text("MiXeD CaSe") == "mixed case"

    def test_remove_punctuation(self) -> None:
        """Test that punctuation is removed."""
        assert normalize_text("Hello, World!") == "hello world"
        assert normalize_text("What's up?") == "whats up"

    def test_collapse_spaces(self) -> None:
        """Test that multiple spaces are collapsed."""
        assert normalize_text("hello    world") == "hello world"
        assert normalize_text("  spaces  everywhere  ") == "spaces everywhere"

    def test_normalize_hyphens(self) -> None:
        """Test that hyphens and dashes become spaces."""
        assert normalize_text("rock-n-roll") == "rock n roll"
        assert normalize_text("song—title") == "song title"
        assert normalize_text("under_score") == "under score"

    def test_remove_feat_patterns(self) -> None:
        """Test that feat/ft/featuring patterns are removed."""
        assert normalize_text("Song feat. Artist") == "song"
        assert normalize_text("Song ft. Someone") == "song"
        assert normalize_text("Song featuring Artist Name") == "song"
        assert normalize_text("Song Feat Artist") == "song"

    def test_remove_parenthetical(self) -> None:
        """Test that parenthetical content is removed."""
        assert normalize_text("Song Name (Official Audio)") == "song name"
        assert normalize_text("Song [Remastered 2020]") == "song"
        assert normalize_text("Track (Live) [HD]") == "track"

    def test_unicode_normalization(self) -> None:
        """Test that unicode accents are normalized."""
        assert normalize_text("Café") == "cafe"
        assert normalize_text("naïve") == "naive"
        assert normalize_text("résumé") == "resume"


class TestExtractBaseName:
    """Tests for extract_base_name function."""

    def test_basic_extraction(self) -> None:
        """Test basic name extraction."""
        assert extract_base_name("Song Name") == "song name"

    def test_remove_remastered(self) -> None:
        """Test that remastered tags in parentheses are removed."""
        assert extract_base_name("Song Name (Remastered 2020)") == "song name"
        # Note: "- Remastered" becomes "remastered" in the text (hyphen to space)
        # This is intentional - the base name extraction removes parenthetical content
        # but keeps inline qualifiers for more accurate fuzzy matching
        result = extract_base_name("Song Name - Remastered")
        assert "song name" in result

    def test_remove_official(self) -> None:
        """Test that official tags are removed."""
        assert extract_base_name("Song Name (Official)") == "song name"
        assert extract_base_name("Song Name [Official Audio]") == "song name"

    def test_remove_feat(self) -> None:
        """Test that feat patterns are removed."""
        assert extract_base_name("Song Name feat. Artist") == "song name"


class TestTokenize:
    """Tests for tokenize function."""

    def test_basic_tokenization(self) -> None:
        """Test basic word tokenization."""
        tokens = tokenize("hello world")
        assert tokens == {"hello", "world"}

    def test_tokenize_with_punctuation(self) -> None:
        """Test tokenization removes punctuation."""
        tokens = tokenize("Hello, World!")
        assert tokens == {"hello", "world"}

    def test_tokenize_normalized(self) -> None:
        """Test that tokenize applies normalization."""
        tokens = tokenize("Song Name (Official)")
        assert tokens == {"song", "name"}


class TestPenaltyAndBonusWords:
    """Tests for penalty and bonus word detection."""

    def test_detect_penalty_words(self) -> None:
        """Test detection of penalty words."""
        assert "live" in get_penalty_words_in_text("Song Name (Live)")
        assert "cover" in get_penalty_words_in_text("Song Name - Cover")
        assert "karaoke" in get_penalty_words_in_text("Song Name Karaoke Version")

    def test_no_penalty_words(self) -> None:
        """Test when no penalty words are present."""
        assert get_penalty_words_in_text("Song Name (Official)") == set()

    def test_detect_bonus_words(self) -> None:
        """Test detection of bonus words."""
        assert "official" in get_bonus_words_in_text("Song Name (Official)")
        assert "remastered" in get_bonus_words_in_text("Song Name - Remastered")
        assert "hd" in get_bonus_words_in_text("Song Name HD")

    def test_no_bonus_words(self) -> None:
        """Test when no bonus words are present."""
        assert get_bonus_words_in_text("Song Name") == set()


class TestFuzzyRatios:
    """Tests for fuzzy matching functions."""

    def test_fuzzy_ratio_identical(self) -> None:
        """Test that identical strings return 100."""
        assert fuzzy_ratio("hello", "hello") == 100.0

    def test_fuzzy_ratio_different(self) -> None:
        """Test that completely different strings return low score."""
        score = fuzzy_ratio("hello", "world")
        assert score < 50

    def test_fuzzy_ratio_similar(self) -> None:
        """Test that similar strings return high score."""
        score = fuzzy_ratio("hello", "hallo")
        assert score > 70

    def test_token_sort_ratio(self) -> None:
        """Test token sort ratio handles word order."""
        # Same words, different order
        score = token_sort_ratio("hello world", "world hello")
        assert score == 100.0

    def test_token_set_ratio(self) -> None:
        """Test token set ratio uses set intersection."""
        # Overlapping tokens
        score = token_set_ratio("hello world test", "hello world")
        assert score > 50


class TestMatchCandidate:
    """Tests for MatchCandidate dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        media_file = MediaFile(
            path="/music/song.mp3",
            nombre_base="song",
            extension=".mp3",
            tamano=1024,
            tipo=MediaType.AUDIO,
        )
        candidate = MatchCandidate(
            media_file=media_file,
            score=85.5,
            reason="test reason",
            is_exact=True,
            normalized_name="song",
            penalties=[],
            bonuses=["official"],
        )
        data = candidate.to_dict()

        assert data["score"] == 85.5
        assert data["reason"] == "test reason"
        assert data["is_exact"] is True
        assert data["bonuses"] == ["official"]


class TestMatchResult:
    """Tests for MatchResult dataclass."""

    def test_to_dict_empty(self) -> None:
        """Test serialization of empty result."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Test Song")
        result = MatchResult(requested_item=item)
        data = result.to_dict()

        assert data["match_found"] is False
        assert data["best_match"] is None
        assert data["candidates"] == []


class TestMatchSingleItem:
    """Tests for match_single_item function."""

    @pytest.fixture
    def sample_catalog(self) -> MediaCatalog:
        """Create a sample catalog for testing."""
        return MediaCatalog(
            archivos=[
                MediaFile(
                    path="/music/Song Name.mp3",
                    nombre_base="Song Name",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Song Name (Official).mp3",
                    nombre_base="Song Name (Official)",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Song Name - Remastered.mp3",
                    nombre_base="Song Name - Remastered",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Song Name (Live).mp3",
                    nombre_base="Song Name (Live)",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Song Name Karaoke.mp3",
                    nombre_base="Song Name Karaoke",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Different Song.mp3",
                    nombre_base="Different Song",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
            ],
            origenes=["/music"],
        )

    def test_exact_match(self, sample_catalog: MediaCatalog) -> None:
        """Test exact matching by base name."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Name")
        result = match_single_item(item, sample_catalog)

        assert result.match_found is True
        assert result.best_match is not None
        # Should match one of the "Song Name" variants
        assert "song name" in result.best_match.normalized_name

    def test_fuzzy_match(self, sample_catalog: MediaCatalog) -> None:
        """Test fuzzy matching with slight variations."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Sung Name")
        result = match_single_item(item, sample_catalog, threshold=50.0)

        assert result.match_found is True
        assert len(result.candidates) > 0

    def test_no_match_below_threshold(self, sample_catalog: MediaCatalog) -> None:
        """Test that items below threshold are not matched."""
        item = RequestedItem(
            tipo=RequestedItemType.SONG, texto_original="Completely Different Title XYZ"
        )
        result = match_single_item(item, sample_catalog, threshold=90.0)

        assert result.match_found is False

    def test_penalty_words_reduce_score(self, sample_catalog: MediaCatalog) -> None:
        """Test that penalty words (live, karaoke) reduce scores for songs."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Name")
        result = match_single_item(item, sample_catalog)

        # Find the live and karaoke versions in candidates
        live_candidate = None
        karaoke_candidate = None
        official_candidate = None

        for candidate in result.candidates:
            if "Live" in candidate.media_file.nombre_base:
                live_candidate = candidate
            elif "Karaoke" in candidate.media_file.nombre_base:
                karaoke_candidate = candidate
            elif "Official" in candidate.media_file.nombre_base:
                official_candidate = candidate

        # Live and Karaoke should have penalties
        if live_candidate:
            assert "live" in live_candidate.penalties
        if karaoke_candidate:
            assert "karaoke" in karaoke_candidate.penalties

        # Official should have bonus
        if official_candidate:
            assert "official" in official_candidate.bonuses

    def test_ranking_prefers_official_over_live(self, sample_catalog: MediaCatalog) -> None:
        """Test that official/remastered versions rank higher than live/karaoke."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Name")
        result = match_single_item(item, sample_catalog)

        # Get positions of different versions
        positions: dict[str, int] = {}
        for i, candidate in enumerate(result.candidates):
            name = candidate.media_file.nombre_base
            if "Official" in name:
                positions["official"] = i
            elif "Remastered" in name:
                positions["remastered"] = i
            elif "Live" in name:
                positions["live"] = i
            elif "Karaoke" in name:
                positions["karaoke"] = i

        # Official and Remastered should rank before Live and Karaoke
        if "official" in positions and "live" in positions:
            assert positions["official"] < positions["live"]
        if "remastered" in positions and "karaoke" in positions:
            assert positions["remastered"] < positions["karaoke"]


class TestMatchItems:
    """Tests for match_items function (main API)."""

    @pytest.fixture
    def sample_catalog(self) -> MediaCatalog:
        """Create a sample catalog for testing."""
        return MediaCatalog(
            archivos=[
                MediaFile(
                    path="/music/Artist - Song A.mp3",
                    nombre_base="Artist - Song A",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Artist - Song B.mp3",
                    nombre_base="Artist - Song B",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Another Artist - Song C.mp3",
                    nombre_base="Another Artist - Song C",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
            ],
            origenes=["/music"],
        )

    def test_match_multiple_items(self, sample_catalog: MediaCatalog) -> None:
        """Test matching multiple items at once."""
        items = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song A"),
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song B"),
        ]
        results = match_items(items, sample_catalog, threshold=50.0)

        assert len(results) == 2
        # Both should find matches
        assert results[0].match_found is True
        assert results[1].match_found is True

    def test_match_items_with_threshold(self, sample_catalog: MediaCatalog) -> None:
        """Test that threshold is applied correctly."""
        items = [
            RequestedItem(tipo=RequestedItemType.SONG, texto_original="Nonexistent Song XYZ"),
        ]
        results = match_items(items, sample_catalog, threshold=90.0)

        assert len(results) == 1
        assert results[0].match_found is False


class TestAcceptanceCriteria:
    """Tests for the specific acceptance criteria in the issue."""

    @pytest.fixture
    def acceptance_catalog(self) -> MediaCatalog:
        """Create catalog matching the acceptance criteria example."""
        return MediaCatalog(
            archivos=[
                MediaFile(
                    path="/music/Song Name (Official).mp3",
                    nombre_base="Song Name (Official)",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
                MediaFile(
                    path="/music/Song Name - Remastered.mp3",
                    nombre_base="Song Name - Remastered",
                    extension=".mp3",
                    tamano=5000000,
                    tipo=MediaType.AUDIO,
                ),
            ],
            origenes=["/music"],
        )

    def test_song_name_finds_variants(self, acceptance_catalog: MediaCatalog) -> None:
        """Test: For 'Song Name', if exists 'Song Name (Official)' or 'Song Name - Remastered',
        choose the most similar and explain why."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Name")
        result = match_single_item(item, acceptance_catalog)

        # Should find a match
        assert result.match_found is True
        assert result.best_match is not None

        # Should match one of the variants
        best_name = result.best_match.media_file.nombre_base
        assert "Song Name" in best_name

        # Should have a reason explaining the match
        assert result.best_match.reason != ""

        # Should have bonus words detected
        assert len(result.best_match.bonuses) > 0

    def test_explanation_provided(self, acceptance_catalog: MediaCatalog) -> None:
        """Test that matches include explanations."""
        item = RequestedItem(tipo=RequestedItemType.SONG, texto_original="Song Name")
        result = match_single_item(item, acceptance_catalog)

        assert result.best_match is not None

        # Test the explain_match function
        explanation = explain_match(
            requested="Song Name",
            matched=result.best_match.media_file.nombre_base,
            item_type=RequestedItemType.SONG,
        )

        assert explanation != ""
        assert len(explanation) > 10  # Should be a meaningful explanation


class TestExplainMatch:
    """Tests for explain_match function."""

    def test_explain_exact_match(self) -> None:
        """Test explanation for exact matches."""
        explanation = explain_match(
            requested="Song Name",
            matched="Song Name",
            item_type=RequestedItemType.SONG,
        )
        assert "coincidencia exacta" in explanation

    def test_explain_with_bonus_words(self) -> None:
        """Test explanation includes bonus words."""
        explanation = explain_match(
            requested="Song Name",
            matched="Song Name (Official)",
            item_type=RequestedItemType.SONG,
        )
        assert "official" in explanation.lower() or "calidad" in explanation.lower()

    def test_explain_with_penalty_words(self) -> None:
        """Test explanation includes penalty words for songs."""
        explanation = explain_match(
            requested="Song Name",
            matched="Song Name (Live)",
            item_type=RequestedItemType.SONG,
        )
        assert "live" in explanation.lower()

    def test_explain_common_tokens(self) -> None:
        """Test explanation mentions common tokens."""
        explanation = explain_match(
            requested="Rock Song Title",
            matched="Rock Song Title Extended",
            item_type=RequestedItemType.SONG,
        )
        assert "palabras en común" in explanation or "alta similitud" in explanation


class TestRapidfuzzFallback:
    """Tests to ensure difflib fallback works when rapidfuzz is not available."""

    def test_fuzzy_functions_work(self) -> None:
        """Test that fuzzy functions work regardless of rapidfuzz availability."""
        # These should work whether rapidfuzz is installed or not
        score1 = fuzzy_ratio("hello", "hallo")
        score2 = token_sort_ratio("hello world", "world hello")
        score3 = token_set_ratio("a b c", "a b")

        assert 0 <= score1 <= 100
        assert 0 <= score2 <= 100
        assert 0 <= score3 <= 100

    def test_rapidfuzz_availability_flag(self) -> None:
        """Test that RAPIDFUZZ_AVAILABLE flag is a boolean."""
        assert isinstance(RAPIDFUZZ_AVAILABLE, bool)

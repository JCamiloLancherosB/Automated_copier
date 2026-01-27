"""Matching engine for comparing requested items with catalog entries."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from mediacopier.core.indexer import MediaCatalog, MediaFile
from mediacopier.core.models import CopyRules, RequestedItem, RequestedItemType

# Try to use rapidfuzz for better fuzzy matching, fallback to difflib
try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz

    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    import difflib


# Patterns to remove from song names for normalization
# Uses word boundary and captures everything until end of string or parenthesis/bracket
FEAT_PATTERNS = re.compile(
    r"\b(?:feat\.?|ft\.?|featuring)\b[\s.]*[^()[\]]*?(?=\s*[\(\[]|$)",
    re.IGNORECASE,
)

# Parenthetical content patterns (for cleanup but also for analysis)
PARENTHETICAL_PATTERN = re.compile(r"\([^)]*\)|\[[^\]]*\]")

# Words that indicate lower-quality versions for songs
PENALTY_WORDS = frozenset({
    "live",
    "cover",
    "karaoke",
    "instrumental",
    "acoustic",
    "demo",
    "remix",
    "bootleg",
    "tribute",
})

# Words that indicate quality/official versions (bonus scoring)
BONUS_WORDS = frozenset({
    "official",
    "remastered",
    "remaster",
    "deluxe",
    "hd",
    "hq",
    "original",
})

# Default exclusion words for filtering junk content
DEFAULT_EXCLUSION_WORDS = frozenset({
    "sample",
    "trailer",
    "camrip",
    "cam",
    "ts",
    "telesync",
    "screener",
    "workprint",
    "hdcam",
    "low quality",
    "lowquality",
    "preview",
    "promo",
    "watermark",
})

# Resolution priority mapping (higher = better)
RESOLUTION_PRIORITY = {
    "2160p": 100,
    "4k": 100,
    "1080p": 80,
    "1080i": 75,
    "720p": 60,
    "720i": 55,
    "576p": 40,
    "576i": 35,
    "480p": 30,
    "480i": 25,
    "360p": 15,
    "240p": 10,
}

# Resolution patterns for extraction from filenames
RESOLUTION_PATTERN = re.compile(
    r"\b(2160p|4k|1080p|1080i|720p|720i|576p|576i|480p|480i|360p|240p)\b",
    re.IGNORECASE,
)


def extract_resolution_from_name(name: str) -> str | None:
    """Extract resolution from a filename or string.

    Args:
        name: The filename or text to analyze.

    Returns:
        Resolution string (e.g., "1080p") or None if not found.
    """
    match = RESOLUTION_PATTERN.search(name)
    if match:
        return match.group(1).lower()
    return None


def get_resolution_score(resolution: str | None, width: int | None, height: int | None) -> int:
    """Calculate a resolution score for quality comparison.

    Args:
        resolution: Resolution string from filename (e.g., "1080p").
        width: Video width in pixels.
        height: Video height in pixels.

    Returns:
        Resolution score (higher = better quality).
    """
    # First try from filename resolution
    if resolution:
        score = RESOLUTION_PRIORITY.get(resolution.lower(), 0)
        if score > 0:
            return score

    # Fall back to video dimensions
    if height is not None:
        if height >= 2160:
            return 100
        elif height >= 1080:
            return 80
        elif height >= 720:
            return 60
        elif height >= 576:
            return 40
        elif height >= 480:
            return 30
        elif height >= 360:
            return 15
        elif height >= 240:
            return 10

    return 0


def contains_exclusion_word(text: str, exclusion_words: list[str]) -> tuple[bool, str | None]:
    """Check if text contains any exclusion word.

    Uses case-insensitive word boundary matching to avoid partial matches.

    Args:
        text: Text to check for exclusion words.
        exclusion_words: List of words/phrases to check for.

    Returns:
        Tuple of (contains_exclusion, matched_word) where matched_word is the
        first exclusion word found, or None if no match.
    """
    if not exclusion_words:
        return False, None

    text_lower = text.lower()
    for word in exclusion_words:
        word_lower = word.strip().lower()
        if not word_lower:
            continue
        # Use word boundary regex for single words, simple contains for phrases
        if " " in word_lower:
            # For phrases, use simple substring matching
            if word_lower in text_lower:
                return True, word
        else:
            # For single words, use word boundary matching
            pattern = rf"\b{re.escape(word_lower)}\b"
            if re.search(pattern, text_lower):
                return True, word
    return False, None


def normalize_text(text: str) -> str:
    """Apply strong normalization for matching.

    Steps:
    1. Convert to lowercase
    2. Normalize unicode characters (accents, etc.)
    3. Remove feat/ft/featuring patterns
    4. Remove punctuation
    5. Collapse multiple spaces
    6. Normalize hyphens/dashes to spaces
    7. Strip leading/trailing whitespace

    Args:
        text: Original text to normalize.

    Returns:
        Normalized text for comparison.
    """
    # Convert to lowercase
    result = text.lower()

    # Normalize unicode characters (remove accents)
    result = unicodedata.normalize("NFKD", result)
    result = "".join(c for c in result if not unicodedata.combining(c))

    # Remove feat/ft/featuring patterns
    result = FEAT_PATTERNS.sub("", result)

    # Remove parenthetical content for base comparison
    result = PARENTHETICAL_PATTERN.sub("", result)

    # Normalize hyphens and dashes to spaces
    result = re.sub(r"[-–—_]+", " ", result)

    # Remove punctuation (keep alphanumeric and spaces)
    result = re.sub(r"[^\w\s]", "", result)

    # Collapse multiple spaces
    result = re.sub(r"\s+", " ", result)

    # Strip whitespace
    return result.strip()


def extract_base_name(text: str) -> str:
    """Extract the base name from a text, removing version suffixes.

    This is used to compare base song/item names without extras like
    "(Remastered 2011)" or "[Official Audio]".

    Args:
        text: Original text.

    Returns:
        Base name without version suffixes.
    """
    # Remove parenthetical and bracket content
    result = PARENTHETICAL_PATTERN.sub("", text)
    # Remove feat patterns
    result = FEAT_PATTERNS.sub("", result)
    # Normalize
    return normalize_text(result)


def tokenize(text: str) -> set[str]:
    """Split normalized text into a set of tokens.

    Args:
        text: Normalized text.

    Returns:
        Set of word tokens.
    """
    normalized = normalize_text(text)
    return set(normalized.split())


def get_penalty_words_in_text(text: str) -> set[str]:
    """Find penalty words present in the text.

    Uses word boundary matching to avoid partial word matches
    (e.g., 'live' won't match in 'delivery').

    Args:
        text: Text to analyze.

    Returns:
        Set of penalty words found in text.
    """
    text_lower = text.lower()
    result = set()
    for word in PENALTY_WORDS:
        # Use word boundary regex to avoid partial matches
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, text_lower):
            result.add(word)
    return result


def get_bonus_words_in_text(text: str) -> set[str]:
    """Find bonus words present in the text.

    Uses word boundary matching to avoid partial word matches
    (e.g., 'official' won't match in 'unofficial').

    Args:
        text: Text to analyze.

    Returns:
        Set of bonus words found in text.
    """
    text_lower = text.lower()
    result = set()
    for word in BONUS_WORDS:
        # Use word boundary regex to avoid partial matches
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, text_lower):
            result.add(word)
    return result


def fuzzy_ratio(str1: str, str2: str) -> float:
    """Calculate fuzzy similarity ratio between two strings.

    Uses rapidfuzz if available, otherwise falls back to difflib.

    Args:
        str1: First string.
        str2: Second string.

    Returns:
        Similarity ratio from 0.0 to 100.0.
    """
    if RAPIDFUZZ_AVAILABLE:
        return rapidfuzz_fuzz.ratio(str1, str2)
    else:
        # difflib returns 0.0-1.0, we need 0-100
        return difflib.SequenceMatcher(None, str1, str2).ratio() * 100


def token_sort_ratio(str1: str, str2: str) -> float:
    """Calculate token sort similarity ratio.

    Sorts words alphabetically before comparing, which helps
    when word order differs.

    Args:
        str1: First string.
        str2: Second string.

    Returns:
        Similarity ratio from 0.0 to 100.0.
    """
    if RAPIDFUZZ_AVAILABLE:
        return rapidfuzz_fuzz.token_sort_ratio(str1, str2)
    else:
        # Manual implementation for difflib fallback
        sorted1 = " ".join(sorted(str1.split()))
        sorted2 = " ".join(sorted(str2.split()))
        return difflib.SequenceMatcher(None, sorted1, sorted2).ratio() * 100


def token_set_ratio(str1: str, str2: str) -> float:
    """Calculate token set similarity ratio.

    Uses set intersection of tokens for comparison.

    Args:
        str1: First string.
        str2: Second string.

    Returns:
        Similarity ratio from 0.0 to 100.0.
    """
    if RAPIDFUZZ_AVAILABLE:
        return rapidfuzz_fuzz.token_set_ratio(str1, str2)
    else:
        # Manual implementation for difflib fallback
        tokens1 = set(str1.split())
        tokens2 = set(str2.split())
        intersection = tokens1 & tokens2
        if not tokens1 or not tokens2:
            return 0.0
        # Jaccard-like similarity
        union = tokens1 | tokens2
        return (len(intersection) / len(union)) * 100


@dataclass
class MatchCandidate:
    """A candidate match from the catalog."""

    media_file: MediaFile
    score: float
    reason: str
    is_exact: bool = False
    normalized_name: str = ""
    penalties: list[str] = field(default_factory=list)
    bonuses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "media_file": self.media_file.to_dict(),
            "score": self.score,
            "reason": self.reason,
            "is_exact": self.is_exact,
            "normalized_name": self.normalized_name,
            "penalties": self.penalties,
            "bonuses": self.bonuses,
        }


@dataclass
class MatchResult:
    """Result of matching a requested item against the catalog."""

    requested_item: RequestedItem
    candidates: list[MatchCandidate] = field(default_factory=list)
    best_match: MatchCandidate | None = None
    match_found: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "requested_item": self.requested_item.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "best_match": self.best_match.to_dict() if self.best_match else None,
            "match_found": self.match_found,
        }


def _calculate_score(
    requested_normalized: str,
    candidate_normalized: str,
    candidate_original: str,
    item_type: RequestedItemType,
) -> tuple[float, str, list[str], list[str]]:
    """Calculate match score between requested item and candidate.

    Scoring factors:
    1. Base fuzzy similarity (multiple algorithms, take best)
    2. Token overlap bonus
    3. Length similarity bonus
    4. Penalty for live/cover/karaoke (if item is a song)
    5. Bonus for official/remastered versions

    Args:
        requested_normalized: Normalized requested text.
        candidate_normalized: Normalized candidate text.
        candidate_original: Original candidate text (for penalty detection).
        item_type: Type of the requested item.

    Returns:
        Tuple of (score, reason, penalties, bonuses).
    """
    penalties: list[str] = []
    bonuses: list[str] = []
    reasons: list[str] = []

    # Calculate multiple fuzzy ratios and use the best
    ratio = fuzzy_ratio(requested_normalized, candidate_normalized)
    token_sort = token_sort_ratio(requested_normalized, candidate_normalized)
    token_set = token_set_ratio(requested_normalized, candidate_normalized)

    # Take the best of different algorithms
    base_score = max(ratio, token_sort, token_set)
    reasons.append(f"similaridad base: {base_score:.1f}%")

    # Token overlap bonus
    req_tokens = tokenize(requested_normalized)
    cand_tokens = tokenize(candidate_normalized)
    if req_tokens and cand_tokens:
        common_tokens = req_tokens & cand_tokens
        token_overlap = len(common_tokens) / max(len(req_tokens), len(cand_tokens))
        token_bonus = token_overlap * 10  # Up to 10 points
        base_score += token_bonus
        if token_bonus > 0:
            reasons.append(f"tokens comunes: {len(common_tokens)}")

    # Length similarity bonus (prefer similar length)
    len_req = len(requested_normalized)
    len_cand = len(candidate_normalized)
    if len_req > 0 and len_cand > 0:
        length_ratio = min(len_req, len_cand) / max(len_req, len_cand)
        length_bonus = length_ratio * 5  # Up to 5 points
        base_score += length_bonus

    # Apply penalties for songs
    if item_type == RequestedItemType.SONG:
        penalty_words_found = get_penalty_words_in_text(candidate_original)
        for word in penalty_words_found:
            base_score -= 15  # Significant penalty
            penalties.append(word)
        if penalties:
            reasons.append(f"penalización por: {', '.join(penalties)}")

    # Apply bonuses for quality indicators
    bonus_words_found = get_bonus_words_in_text(candidate_original)
    for word in bonus_words_found:
        base_score += 5  # Small bonus
        bonuses.append(word)
    if bonuses:
        reasons.append(f"bonus por: {', '.join(bonuses)}")

    # Clamp score to 0-100 range
    final_score = max(0.0, min(100.0, base_score))

    reason = "; ".join(reasons)
    return final_score, reason, penalties, bonuses


def match_single_item(
    item: RequestedItem,
    catalog: MediaCatalog,
    threshold: float = 60.0,
    max_candidates: int = 10,
    rules: CopyRules | None = None,
) -> MatchResult:
    """Match a single requested item against the catalog.

    Args:
        item: The requested item to match.
        catalog: Media catalog to search.
        threshold: Minimum similarity threshold (0-100).
        max_candidates: Maximum number of candidates to return.
        rules: Optional copy rules for filtering by exclusion words.

    Returns:
        MatchResult with ranked candidates.
    """
    from mediacopier.core.indexer import MediaType

    result = MatchResult(requested_item=item)
    requested_normalized = normalize_text(item.texto_original)
    requested_base = extract_base_name(item.texto_original)

    # Get exclusion words from rules or use defaults
    exclusion_words: list[str] = []
    if rules and rules.excluir_palabras:
        exclusion_words = rules.excluir_palabras
    else:
        exclusion_words = list(DEFAULT_EXCLUSION_WORDS)

    candidates: list[MatchCandidate] = []

    for media_file in catalog.archivos:
        # Check exclusion words - skip files with junk content
        if exclusion_words:
            is_excluded, excluded_word = contains_exclusion_word(
                media_file.nombre_base, exclusion_words
            )
            if is_excluded:
                continue  # Skip this file, it contains an exclusion word

        # Check extension whitelist/blacklist by media type if rules provided
        if rules:
            ext = media_file.extension.lower()
            # Helper to normalize extension (remove single leading dot)
            ext_no_dot = ext[1:] if ext.startswith(".") else ext
            if media_file.tipo == MediaType.AUDIO:
                # Check audio blacklist
                if rules.extensiones_audio_bloqueadas:
                    blocked = [e.lower() for e in rules.extensiones_audio_bloqueadas]
                    blocked_normalized = []
                    for b in blocked:
                        blocked_normalized.append(b)
                        # Also add version with/without leading dot
                        if b.startswith("."):
                            blocked_normalized.append(b[1:])
                        else:
                            blocked_normalized.append(f".{b}")
                    if ext in blocked_normalized or ext_no_dot in blocked_normalized:
                        continue
                # Check audio whitelist (if specified, only allow these)
                if rules.extensiones_audio_permitidas:
                    allowed = [e.lower() for e in rules.extensiones_audio_permitidas]
                    allowed_normalized = [e if e.startswith(".") else f".{e}" for e in allowed]
                    if ext not in allowed_normalized:
                        continue
            elif media_file.tipo == MediaType.VIDEO:
                # Check video blacklist
                if rules.extensiones_video_bloqueadas:
                    blocked = [e.lower() for e in rules.extensiones_video_bloqueadas]
                    blocked_normalized = []
                    for b in blocked:
                        blocked_normalized.append(b)
                        # Also add version with/without leading dot
                        if b.startswith("."):
                            blocked_normalized.append(b[1:])
                        else:
                            blocked_normalized.append(f".{b}")
                    if ext in blocked_normalized or ext_no_dot in blocked_normalized:
                        continue
                # Check video whitelist (if specified, only allow these)
                if rules.extensiones_video_permitidas:
                    allowed = [e.lower() for e in rules.extensiones_video_permitidas]
                    allowed_normalized = [e if e.startswith(".") else f".{e}" for e in allowed]
                    if ext not in allowed_normalized:
                        continue

        candidate_normalized = normalize_text(media_file.nombre_base)
        candidate_base = extract_base_name(media_file.nombre_base)

        # Check for exact match (normalized base names are equal)
        is_exact = (requested_base == candidate_base) or (
            requested_normalized == candidate_normalized
        )

        # Calculate score
        score, reason, penalties, bonuses = _calculate_score(
            requested_normalized,
            candidate_normalized,
            media_file.nombre_base,
            item.tipo,
        )

        # Apply movie quality scoring for MOVIE type
        if item.tipo == RequestedItemType.MOVIE and rules:
            resolution_from_name = extract_resolution_from_name(media_file.nombre_base)
            video_width = None
            video_height = None
            video_codec = None

            if media_file.video_meta:
                video_width = media_file.video_meta.width
                video_height = media_file.video_meta.height
                video_codec = media_file.video_meta.codec

            # Add resolution bonus if preferring high resolution
            if rules.preferir_resolucion_alta:
                res_score = get_resolution_score(resolution_from_name, video_width, video_height)
                # Add bonus based on resolution (up to 10 points)
                resolution_bonus = (res_score / 100.0) * 10
                score += resolution_bonus
                if res_score > 0:
                    if resolution_from_name:
                        res_str = resolution_from_name
                    elif video_height:
                        res_str = f"{video_height}p"
                    else:
                        res_str = "unknown"
                    reason += f"; resolución: {res_str} (+{resolution_bonus:.1f})"

            # Add codec preference bonus
            if rules.codecs_preferidos and video_codec:
                codec_lower = video_codec.lower()
                for i, preferred in enumerate(rules.codecs_preferidos):
                    if preferred.lower() in codec_lower:
                        # Earlier in list = more preferred
                        codec_bonus = 5 - (i * 0.5)  # 5, 4.5, 4, 3.5...
                        codec_bonus = max(0, codec_bonus)
                        score += codec_bonus
                        reason += f"; codec preferido: {video_codec} (+{codec_bonus:.1f})"
                        break

        if is_exact:
            score = max(score, 95.0)  # Exact matches get high base score
            reason = f"coincidencia exacta; {reason}"

        # Skip if below threshold (unless exact match)
        if score < threshold and not is_exact:
            continue

        candidate = MatchCandidate(
            media_file=media_file,
            score=score,
            reason=reason,
            is_exact=is_exact,
            normalized_name=candidate_normalized,
            penalties=penalties,
            bonuses=bonuses,
        )
        candidates.append(candidate)

    # Sort by score (descending), then by whether it's exact
    candidates.sort(key=lambda c: (c.score, c.is_exact), reverse=True)

    # Limit candidates
    result.candidates = candidates[:max_candidates]

    if result.candidates:
        result.best_match = result.candidates[0]
        result.match_found = True

    return result


def match_items(
    requested_items: list[RequestedItem],
    catalog: MediaCatalog,
    rules: CopyRules | None = None,
    threshold: float = 60.0,
    max_candidates: int = 10,
) -> list[MatchResult]:
    """Match multiple requested items against the catalog.

    This is the main API function for the matching engine.

    Args:
        requested_items: List of items to match.
        catalog: Media catalog to search against.
        rules: Optional copy rules for filtering and selection options.
        threshold: Minimum similarity threshold (0-100).
        max_candidates: Maximum number of candidates per item.

    Returns:
        List of MatchResult objects, one per requested item.
    """
    results: list[MatchResult] = []

    # Determine effective max candidates based on rules
    effective_max_candidates = max_candidates
    if rules and rules.solo_mejor_match:
        effective_max_candidates = 1

    for item in requested_items:
        result = match_single_item(
            item=item,
            catalog=catalog,
            threshold=threshold,
            max_candidates=effective_max_candidates,
            rules=rules,
        )
        results.append(result)

    return results


def explain_match(requested: str, matched: str, item_type: RequestedItemType) -> str:
    """Generate a human-readable explanation of why a match was chosen.

    Args:
        requested: Original requested text.
        matched: The matched text.
        item_type: Type of item being matched.

    Returns:
        Human-readable explanation string.
    """
    req_normalized = normalize_text(requested)
    match_normalized = normalize_text(matched)
    match_base = extract_base_name(matched)

    explanations: list[str] = []

    # Check for exact match
    if req_normalized == match_normalized or req_normalized == match_base:
        explanations.append(f'"{matched}" es una coincidencia exacta del nombre base')

    # Check for common tokens
    req_tokens = tokenize(requested)
    match_tokens = tokenize(matched)
    common = req_tokens & match_tokens
    if common:
        common_str = ", ".join(sorted(common))
        explanations.append(f"comparte {len(common)} palabras en común: {common_str}")

    # Check for quality indicators
    bonuses = get_bonus_words_in_text(matched)
    if bonuses:
        explanations.append(f"tiene indicadores de calidad: {', '.join(bonuses)}")

    # Check for penalties
    if item_type == RequestedItemType.SONG:
        penalties = get_penalty_words_in_text(matched)
        if penalties:
            explanations.append(f"NOTA: contiene: {', '.join(penalties)} (puntuación reducida)")

    if not explanations:
        explanations.append(f'"{matched}" tiene alta similitud con "{requested}"')

    return "; ".join(explanations)

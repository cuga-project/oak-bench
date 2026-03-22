"""
Test Scoring Module for Cuga Evaluations

This module provides detailed scoring functionality for evaluating agent responses.
It can be optionally integrated with evaluation loops to provide:
- Keyword matching scores
- Tool call comparison scores
- Response similarity scores using multiple algorithms

Usage:
    # In your evaluation loop, optionally import and use:
    from calculate_test_score import evaluate_test_and_details, TestScore, TestScoreDetails, ToolCall

    # Then call evaluate_test_and_details() to get detailed scores
    score, details = evaluate_test_and_details(
        expected_keywords=["keyword1", "keyword2"],
        tool_calls=actual_tool_calls,
        expected_tool_calls=expected_tool_calls,
        response=agent_response,
        expected_response=expected_response,
    )

Note: This module has minimal dependencies and can be used standalone.
If you don't need detailed scoring, you can simply not import it.
"""

from typing import Tuple, Dict, Any, List, Optional
from collections import Counter
from difflib import SequenceMatcher
from pydantic import BaseModel
from enum import Enum
import json
import re

# Optional dependency - only needed if using MCP tools
try:
    from cuga.backend.tools_env.registry.mcp_manager.adapter import sanitize_tool_name

    HAS_CUGA = True
except ImportError:
    HAS_CUGA = False

    # Fallback implementation if cuga is not available
    def sanitize_tool_name(name: str) -> str:
        """Fallback sanitization if cuga is not available."""
        return name.replace("-", "_").replace(" ", "_").lower()


# Optional dependency - only needed for advanced fuzzy matching
try:
    from rapidfuzz import fuzz, distance

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


class ToolCall(BaseModel):
    """
    Basic model for a tool call
    """

    name: str
    args: Dict


class ScoringMethod(str, Enum):
    """Available scoring methods for response comparison."""

    EXACT = "exact"
    SEQUENCE_MATCHER = "sequence_matcher"
    JACCARD = "jaccard"
    COSINE = "cosine"
    FUZZY_PARTIAL = "fuzzy_partial"
    FUZZY_TOKEN_SET = "fuzzy_token_set"
    JARO_WINKLER = "jaro_winkler"
    LEVENSHTEIN_NORM = "levenshtein_norm"


class ToolCallMismatchType(str, Enum):
    """Types of tool call mismatches."""

    ARGS_MISMATCH = "args_mismatch"
    NAME_MISMATCH = "name_mismatch"
    MISSING = "missing"
    UNEXPECTED = "unexpected"


class ToolCallMismatch(BaseModel):
    """Details about a tool call mismatch."""

    tool_name: str
    type: ToolCallMismatchType
    expected: Optional[ToolCall] = None
    actual: Optional[ToolCall] = None


class TestScore(BaseModel):
    """
    Basic model for test score
    """

    keyword_score: float
    tool_call_score: float
    response_score: float
    response_scoring_type: ScoringMethod


class TestScoreDetails(BaseModel):
    """
    Detailed artifacts to inspect why a test scored the way it did.
    """

    missing_keywords: List[str]
    expected_keywords: List[str]
    expected_tool_calls: List[ToolCall]
    tool_call_mismatches: List[ToolCallMismatch]
    response_expected: str
    response_actual: str
    response_scoring_type: ScoringMethod


# ========== Helper Functions ==========


def _normalize_tokens(s: str) -> List[str]:
    """Normalize text to tokens for comparison."""
    return [
        t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in s).split() if t
    ]


def _jaccard(a_tokens: List[str], b_tokens: List[str]) -> float:
    """Calculate Jaccard similarity between token sets."""
    a, b = set(a_tokens), set(b_tokens)
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def _cosine_tf(a_tokens: List[str], b_tokens: List[str]) -> float:
    """Calculate cosine similarity using term frequency."""
    if not a_tokens and not b_tokens:
        return 1.0
    from collections import Counter as C

    ca, cb = C(a_tokens), C(b_tokens)
    dot = sum(ca[k] * cb.get(k, 0) for k in ca)
    na = sum(v * v for v in ca.values()) ** 0.5
    nb = sum(v * v for v in cb.values()) ** 0.5
    return (dot / (na * nb)) if na and nb else 0.0


def _sequence_matcher(a: str, b: str) -> float:
    """Calculate similarity using SequenceMatcher."""
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ========== 1) Keyword scoring ==========


def score_keywords(
    answer: str, expected_keywords: List[str]
) -> Tuple[float, List[str]]:
    """
    Calculate how many expected keywords appear in the given text.
    Matching is case-insensitive and ignores punctuation/formatting.

    Args:
        answer: The text to search for keywords
        expected_keywords: List of keywords that should appear

    Returns:
        Tuple of (score, missing_keywords)
        - score: float between 0 and 1
        - missing_keywords: list of keywords not found
    """
    if not expected_keywords:
        return 1.0, []

    # Normalize the text: lowercase + remove punctuation
    normalized_text = re.sub(r"[^a-z0-9]+", " ", answer.lower())

    missing_keywords = []
    for kw in expected_keywords:
        normalized_kw = re.sub(r"[^a-z0-9]+", " ", kw.lower()).strip()
        if normalized_kw not in normalized_text:
            missing_keywords.append(kw)

    found = len(expected_keywords) - len(missing_keywords)
    score = found / len(expected_keywords)

    return round(score, 4), missing_keywords


# ========== 2) Response proximity ==========


def score_response(
    actual: str, expected: str, method: ScoringMethod = ScoringMethod.SEQUENCE_MATCHER
) -> Tuple[float, ScoringMethod]:
    """
    Calculate similarity between actual and expected responses.

    Args:
        actual: The actual response text
        expected: The expected response text
        method: The scoring method to use

    Returns:
        Tuple of (score, method_used)
        - score: float between 0 and 1
        - method_used: the ScoringMethod that was applied
    """
    if method == ScoringMethod.EXACT:
        return (1.0 if actual == expected else 0.0), ScoringMethod.EXACT

    if method == ScoringMethod.SEQUENCE_MATCHER:
        return _sequence_matcher(actual, expected), ScoringMethod.SEQUENCE_MATCHER

    if method in {ScoringMethod.JACCARD, ScoringMethod.COSINE}:
        toks_a, toks_b = _normalize_tokens(actual), _normalize_tokens(expected)
        if method == ScoringMethod.JACCARD:
            return _jaccard(toks_a, toks_b), ScoringMethod.JACCARD
        return _cosine_tf(toks_a, toks_b), ScoringMethod.COSINE

    # Advanced fuzzy methods require rapidfuzz
    if not HAS_RAPIDFUZZ:
        # Fallback to sequence matcher if rapidfuzz not available
        return _sequence_matcher(actual, expected), ScoringMethod.SEQUENCE_MATCHER

    if method == ScoringMethod.FUZZY_PARTIAL:
        # robust to extra prefixes/suffixes; good for "expected snippet within longer response"
        return round(
            fuzz.partial_ratio(expected, actual) / 100.0, 4
        ), ScoringMethod.FUZZY_PARTIAL

    if method == ScoringMethod.FUZZY_TOKEN_SET:
        # ignores word order and duplicates—great for rephrased responses
        return round(
            fuzz.token_set_ratio(expected, actual) / 100.0, 4
        ), ScoringMethod.FUZZY_TOKEN_SET

    if method == ScoringMethod.JARO_WINKLER:
        # typo-friendly; higher for small transpositions; normalized 0..1
        jw = distance.JaroWinkler.normalized_similarity(expected, actual)
        return round(float(jw), 4), ScoringMethod.JARO_WINKLER

    if method == ScoringMethod.LEVENSHTEIN_NORM:
        # classic edit distance normalized to 0..1 similarity
        sim = distance.Levenshtein.normalized_similarity(expected, actual)
        return round(float(sim), 4), ScoringMethod.LEVENSHTEIN_NORM

    # default fallback
    return _sequence_matcher(actual, expected), ScoringMethod.SEQUENCE_MATCHER


# ========== 3) Tool call scoring ==========


def _canon_args(d: Dict[str, Any]) -> str:
    """Canonicalize arguments dict to string for comparison."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def _canon(tc: ToolCall) -> Tuple[str, str]:
    """Get canonical representation of a tool call."""
    return (tc.name, _canon_args(tc.args))


def _key(tc: ToolCall) -> Tuple[str, str]:
    """Canonical key (name + normalized args) for comparing tool calls."""
    return _canon(tc)


def score_tool_calls_exact(
    actual: List[ToolCall],
    expected: List[ToolCall],
) -> Tuple[float, List[ToolCallMismatch]]:
    """
    Exact multiset match of (name, args).

    Scoring:
      matched = sum over keys of min(count_actual, count_expected)
      unexpected_count = sum((c_act - c_exp).values())   # extras in actual
      expected_count   = len(expected)
      score = 1.0 if (expected_count == 0 and unexpected_count == 0) else matched / (expected_count + unexpected_count)

    Mismatches (typed):
      - ARGS_MISMATCH (same tool name, different args)
      - NAME_MISMATCH (different tool used instead of expected)
      - MISSING       (expected not called)
      - UNEXPECTED    (called but not expected)

    Args:
        actual: List of actual tool calls made
        expected: List of expected tool calls

    Returns:
        Tuple of (score, mismatches)
        - score: float between 0 and 1
        - mismatches: list of ToolCallMismatch objects
    """
    # sanitize tool names
    for tool_call in expected:
        tool_call.name = sanitize_tool_name(tool_call.name)

    exp_keys = [_key(tc) for tc in expected]
    act_keys = [_key(tc) for tc in actual]
    c_exp, c_act = Counter(exp_keys), Counter(act_keys)

    matched = sum(min(c_exp[k], c_act.get(k, 0)) for k in c_exp)
    unexpected_count = sum((c_act - c_exp).values())
    expected_count = len(expected)

    if expected_count == 0 and unexpected_count == 0:
        score = 1.0
    else:
        denom = expected_count + unexpected_count
        score = (matched / denom) if denom else 1.0

    # Build unmatched lists for detailed mismatch reporting
    def expand_unmatched(
        counter_a: Counter, counter_b: Counter, source_list: List[ToolCall]
    ) -> List[ToolCall]:
        leftover = counter_a - counter_b
        need: List[ToolCall] = []
        by_key: Dict[Tuple[str, str], List[ToolCall]] = {}
        for tc in source_list:
            by_key.setdefault(_key(tc), []).append(tc)
        for k, cnt in leftover.items():
            pool = by_key.get(k, [])
            need.extend(pool[:cnt])
        return need

    unmatched_expected = expand_unmatched(c_exp, c_act, expected)
    unmatched_actual = expand_unmatched(c_act, c_exp, actual)

    mismatches: List[ToolCallMismatch] = []

    # 1) Flag args mismatches first (same tool name, different args)
    #    Greedy, deterministic (left-to-right).
    used_a = set()
    still_ue: List[ToolCall] = []
    for e in unmatched_expected:
        found_ai = None
        for ai, a in enumerate(unmatched_actual):
            if ai in used_a:
                continue
            if a.name == e.name and a.args != e.args:
                mismatches.append(
                    ToolCallMismatch(
                        tool_name=e.name,
                        type=ToolCallMismatchType.ARGS_MISMATCH,
                        expected=e.model_dump(),
                        actual=a.model_dump(),
                    )
                )
                used_a.add(ai)
                found_ai = ai
                break
        if found_ai is None:
            still_ue.append(e)

    still_ua: List[ToolCall] = [
        a for ai, a in enumerate(unmatched_actual) if ai not in used_a
    ]
    unmatched_expected, unmatched_actual = still_ue, still_ua

    # 2) Pair remaining as name mismatches (A instead of B)
    #    Pair in order to stay deterministic.
    for e, a in zip(unmatched_expected, unmatched_actual):
        mismatches.append(
            ToolCallMismatch(
                tool_name=e.name,  # expected tool name
                type=ToolCallMismatchType.NAME_MISMATCH,
                expected=e.model_dump(),
                actual=a.model_dump(),
            )
        )

    # 3) Any leftovers after pairing are pure missing/unexpected
    if len(unmatched_expected) > len(unmatched_actual):
        for e in unmatched_expected[len(unmatched_actual) :]:
            mismatches.append(
                ToolCallMismatch(
                    tool_name=e.name,
                    type=ToolCallMismatchType.MISSING,
                    expected=e.model_dump(),
                    actual=None,
                )
            )
    elif len(unmatched_actual) > len(unmatched_expected):
        for a in unmatched_actual[len(unmatched_expected) :]:
            mismatches.append(
                ToolCallMismatch(
                    tool_name=a.name,
                    type=ToolCallMismatchType.UNEXPECTED,
                    expected=None,
                    actual=a.model_dump(),
                )
            )

    return round(score, 4), mismatches


# ========== Orchestrators ==========


def evaluate_test(
    expected_keywords: List[str],
    tool_calls: List[ToolCall],
    expected_tool_calls: List[ToolCall],
    response: str,
    expected_response: str,
    response_scoring_type: ScoringMethod = ScoringMethod.FUZZY_TOKEN_SET,
) -> TestScore:
    """
    Evaluate a test case and return only the scores.

    This is a simplified version that returns only TestScore without details.
    Use evaluate_test_and_details() if you need detailed mismatch information.

    Args:
        expected_keywords: Keywords that should appear in response
        tool_calls: Actual tool calls made by the agent
        expected_tool_calls: Expected tool calls
        response: Actual response text
        expected_response: Expected response text
        response_scoring_type: Method to use for response comparison

    Returns:
        TestScore object with keyword_score, tool_call_score, and response_score
    """
    kw_score, _missing_keywords = score_keywords(response, expected_keywords)
    tc_score, _tc_mismatches = score_tool_calls_exact(tool_calls, expected_tool_calls)
    resp_score, resp_method = score_response(
        response, expected_response, method=response_scoring_type
    )

    return TestScore(
        keyword_score=round(kw_score, 4),
        tool_call_score=round(tc_score, 4),
        response_score=round(resp_score, 4),
        response_scoring_type=resp_method,
    )


def evaluate_test_and_details(
    expected_keywords: List[str],
    tool_calls: List[ToolCall],
    expected_tool_calls: List[ToolCall],
    response: str,
    expected_response: str,
    response_scoring_type: ScoringMethod = ScoringMethod.FUZZY_TOKEN_SET,
) -> Tuple[TestScore, TestScoreDetails]:
    """
    Evaluate a test case and return both scores and detailed information.

    This is the recommended function to use as it provides both scores and
    detailed information about what went wrong (missing keywords, tool call
    mismatches, etc.).

    Args:
        expected_keywords: Keywords that should appear in response
        tool_calls: Actual tool calls made by the agent
        expected_tool_calls: Expected tool calls
        response: Actual response text
        expected_response: Expected response text
        response_scoring_type: Method to use for response comparison

    Returns:
        Tuple of (TestScore, TestScoreDetails)
        - TestScore: Contains the numeric scores
        - TestScoreDetails: Contains detailed mismatch information
    """
    kw_score, missing_keywords = score_keywords(response, expected_keywords)
    tc_score, tc_mismatches = score_tool_calls_exact(tool_calls, expected_tool_calls)
    resp_score, resp_method = score_response(
        response, expected_response, method=response_scoring_type
    )

    score = TestScore(
        keyword_score=round(kw_score, 4),
        tool_call_score=round(tc_score, 4),
        response_score=round(resp_score, 4),
        response_scoring_type=resp_method,
    )
    details = TestScoreDetails(
        expected_keywords=expected_keywords,
        missing_keywords=missing_keywords,
        expected_tool_calls=expected_tool_calls,
        tool_call_mismatches=tc_mismatches,
        response_expected=expected_response,
        response_actual=response,
        response_scoring_type=resp_method,
    )
    return score, details


# ========== Standalone Usage Example ==========

if __name__ == "__main__":
    # Example usage
    print("Testing calculate_test_score module...")

    # Example 1: Keyword scoring
    response = "The patient needs an MRI scan at the downtown facility."
    keywords = ["MRI", "downtown"]
    kw_score, missing = score_keywords(response, keywords)
    print(f"\nKeyword Score: {kw_score}")
    print(f"Missing Keywords: {missing}")

    # Example 2: Tool call scoring
    expected_calls = [
        ToolCall(
            name="search_providers", args={"service": "MRI", "location": "downtown"}
        ),
    ]
    actual_calls = [
        ToolCall(
            name="search_providers", args={"service": "MRI", "location": "downtown"}
        ),
    ]
    tc_score, mismatches = score_tool_calls_exact(actual_calls, expected_calls)
    print(f"\nTool Call Score: {tc_score}")
    print(f"Mismatches: {len(mismatches)}")

    # Example 3: Full evaluation
    score, details = evaluate_test_and_details(
        expected_keywords=keywords,
        tool_calls=actual_calls,
        expected_tool_calls=expected_calls,
        response=response,
        expected_response="The patient needs an MRI scan at the downtown facility.",
        response_scoring_type=ScoringMethod.FUZZY_TOKEN_SET,
    )
    print(f"\nFull Evaluation:")
    print(f"  Keyword Score: {score.keyword_score}")
    print(f"  Tool Call Score: {score.tool_call_score}")
    print(f"  Response Score: {score.response_score}")
    print(f"  Scoring Method: {score.response_scoring_type}")

    print("\n✅ Module is working correctly!")

"""Evaluation metrics for agent performance."""

from typing import Dict, Any, List, Literal
from difflib import SequenceMatcher

# Similarity method type
SimilarityMethod = Literal[
    "sequencematcher",
    "rapidfuzz_wratio",
    "rapidfuzz_token_set",
    "rapidfuzz_partial",
]


class EvaluationMetrics:
    """Computes evaluation metrics for agent responses."""

    @staticmethod
    def exact_match(predicted: str, expected: str) -> bool:
        """Check if predicted exactly matches expected."""
        return predicted.strip().lower() == expected.strip().lower()

    @staticmethod
    def string_similarity(
        predicted: str,
        expected: str,
        method: SimilarityMethod = "rapidfuzz_token_set",
    ) -> float:
        """
        Compute string similarity using the specified method.

        Args:
            predicted: The agent's output text.
            expected: The expected output text.
            method: Similarity method to use:
                - "sequencematcher": Python's difflib SequenceMatcher
                - "rapidfuzz_wratio": RapidFuzz weighted ratio
                - "rapidfuzz_token_set": RapidFuzz token set ratio
                - "rapidfuzz_partial": RapidFuzz partial ratio

        Returns:
            Similarity score between 0 and 1.
        """
        predicted_lower = predicted.lower()
        expected_lower = expected.lower()

        if method == "sequencematcher":
            return SequenceMatcher(None, predicted_lower, expected_lower).ratio()

        # RapidFuzz methods
        return EvaluationMetrics._rapidfuzz_similarity(
            predicted_lower, expected_lower, method
        )

    @staticmethod
    def _rapidfuzz_similarity(predicted: str, expected: str, method: str) -> float:
        """
        Compute similarity using RapidFuzz.

        Args:
            predicted: Lowercased predicted text.
            expected: Lowercased expected text.
            method: RapidFuzz method name.

        Returns:
            Similarity score between 0 and 1.
        """
        try:
            from rapidfuzz import fuzz

            methods = {
                "rapidfuzz_wratio": fuzz.WRatio,
                "rapidfuzz_token_set": fuzz.token_set_ratio,
                "rapidfuzz_partial": fuzz.partial_ratio,
            }

            func = methods.get(method, fuzz.WRatio)
            # RapidFuzz returns 0-100, normalize to 0-1
            return func(predicted, expected) / 100.0

        except ImportError:
            # Fall back to SequenceMatcher if RapidFuzz not available
            return SequenceMatcher(None, predicted, expected).ratio()

    @staticmethod
    def api_calls_match(
        predicted_apis: List[str], expected_apis: str
    ) -> Dict[str, Any]:
        """
        Check if predicted API calls match expected APIs.

        Args:
            predicted_apis: List of API endpoints called by agent.
            expected_apis: Expected APIs (comma-separated string or description).

        Returns:
            Dict with match status and details.
        """
        # Parse expected APIs
        if not expected_apis or expected_apis.lower() == "none":
            expected = []
        else:
            expected = [api.strip() for api in expected_apis.split(",")]

        # Normalize API names (remove /tools/ prefix and trailing /)
        def normalize(api: str) -> str:
            api = api.strip().lower()
            api = api.replace("/tools/", "")
            api = api.rstrip("/")
            return api

        predicted_normalized = set(normalize(api) for api in predicted_apis)
        expected_normalized = set(normalize(api) for api in expected)

        correct = predicted_normalized == expected_normalized
        missing = expected_normalized - predicted_normalized
        extra = predicted_normalized - expected_normalized

        return {
            "correct": correct,
            "missing": list(missing),
            "extra": list(extra),
            "predicted": list(predicted_normalized),
            "expected": list(expected_normalized),
        }

    @staticmethod
    def api_count_match(predicted_count: int, expected_count: Any) -> Dict[str, Any]:
        """
        Check if predicted API call count matches expected.

        Args:
            predicted_count: Number of API calls made.
            expected_count: Expected number (int or string like "N (loop)").

        Returns:
            Dict with match status and details.
        """
        # Handle special cases like "N (loop)" or "5 APIs (multiple calls due to loops)"
        if isinstance(expected_count, str):
            # Extract number from strings like "N (loop)" or "5 APIs"
            import re

            match = re.search(r"\d+", expected_count)
            if match:
                expected = int(match.group())
            else:
                # For "N (loop)", we can't check exactly, so be lenient
                return {
                    "correct": True,
                    "predicted": predicted_count,
                    "expected": expected_count,
                    "note": "Expected count is variable (loop-based)",
                }
        else:
            expected = int(expected_count)

        # Lenient check: correct if predicted >= expected (all expected APIs were called)
        return {
            "correct": predicted_count >= expected,
            "predicted": predicted_count,
            "expected": expected,
        }

    @staticmethod
    def evaluate_output(
        predicted: str,
        expected: str,
        method: SimilarityMethod = "rapidfuzz_token_set",
    ) -> Dict[str, Any]:
        """
        Evaluate output against ground truth.

        Returns:
            Dict with similarity score and match status.
        """
        similarity = EvaluationMetrics.string_similarity(
            predicted, expected, method=method
        )
        exact = EvaluationMetrics.exact_match(predicted, expected)

        return {
            "exact_match": exact,
            "similarity": similarity,
            "predicted": predicted,
            "expected": expected,
        }

    @staticmethod
    def _normalize_unicode(text: str) -> str:
        """
        Normalize unicode characters in text for consistent matching.

        Handles:
        - Narrow no-break space (U+202F) -> regular space
        - Non-breaking space (U+00A0) -> regular space
        - Various dash characters -> standard hyphen
        - Unicode normalization to NFC form
        """
        import unicodedata

        # Normalize to NFC form first
        text = unicodedata.normalize("NFC", text)

        # Replace special spaces with regular spaces
        text = text.replace("\u202f", " ")  # Narrow no-break space
        text = text.replace("\u00a0", " ")  # Non-breaking space
        text = text.replace("\u2009", " ")  # Thin space

        # Replace various dashes with standard hyphen
        text = text.replace("\u2013", "-")  # En dash
        text = text.replace("\u2014", "-")  # Em dash
        text = text.replace("\u2212", "-")  # Minus sign

        return text

    @staticmethod
    def _normalize_for_keyword_match(text: str) -> str:
        """
        Normalize text for keyword matching.

        - Unicode normalization and dash/space normalization
        - Strip markdown/punctuation
        - Collapse whitespace
        """
        import re

        text = EvaluationMetrics._normalize_unicode(text)
        text = text.lower()
        # Remove common markdown emphasis characters
        text = re.sub(r"[`*_~]", "", text)
        # Replace punctuation with spaces to allow loose matching (e.g., time-to-fill -> time to fill)
        #
        # IMPORTANT: Preserve '|' so keywords like "requisition|req" can be treated as OR-alternatives
        # in `keywords_match()` after normalization.
        text = re.sub(r"[^\w\s%|]", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def keywords_match(predicted: str, expected_keywords: List[str]) -> Dict[str, Any]:
        """
        Check if expected keywords appear in the predicted output.

        Keywords are matched case-insensitively with unicode normalization.
        Each keyword is checked for presence as a substring in the output.

        OR alternatives: Keywords containing "|" are treated as alternatives
        where any one match is sufficient. Example: "1000|1,000" matches if
        either "1000" or "1,000" appears in the output.

        Regex keywords: Prefix with "re:" to treat the remainder as a regular
        expression (case-insensitive). Example: "re:can't|cannot|unable".

        Args:
            predicted: The agent's output text.
            expected_keywords: List of keywords that should appear in the output.
                             Use "|" to separate alternatives (e.g., "1000|1,000").

        Returns:
            Dict with:
                - matched: List of keywords found in output
                - missing: List of keywords not found in output
                - match_count: Number of keywords found
                - total_keywords: Total number of expected keywords
                - match_ratio: Ratio of matched to total (0.0 to 1.0)
        """
        if not expected_keywords:
            return {
                "matched": [],
                "missing": [],
                "match_count": 0,
                "total_keywords": 0,
                "match_ratio": 1.0,  # No keywords expected = perfect match
            }

        # Normalize the predicted text
        predicted_normalized = EvaluationMetrics._normalize_for_keyword_match(predicted)

        matched = []
        missing = []

        for keyword in expected_keywords:
            # Regex keyword support (prefix: re:)
            if keyword.strip().lower().startswith("re:"):
                import re

                pattern = keyword.strip()[3:]
                if re.search(pattern, predicted_normalized, flags=re.IGNORECASE):
                    matched.append(keyword)
                else:
                    missing.append(keyword)
                continue

            # Normalize the keyword
            keyword_normalized = EvaluationMetrics._normalize_for_keyword_match(keyword)

            # Check for OR alternatives (e.g., "1000|1,000")
            if "|" in keyword_normalized:
                alternatives = [alt.strip() for alt in keyword_normalized.split("|")]
                if any(alt in predicted_normalized for alt in alternatives):
                    matched.append(keyword)
                else:
                    missing.append(keyword)
            else:
                keyword_lower = keyword_normalized.strip()
                if keyword_lower in predicted_normalized:
                    matched.append(keyword)
                else:
                    missing.append(keyword)

        total = len(expected_keywords)
        match_count = len(matched)

        return {
            "matched": matched,
            "missing": missing,
            "match_count": match_count,
            "total_keywords": total,
            "match_ratio": match_count / total if total > 0 else 1.0,
        }

    @staticmethod
    def evaluate_error_handling(
        response: str,
        expected_behavior: dict,
    ) -> Dict[str, Any]:
        """
        Evaluate how well agent handled error conditions (supplementary metric).

        This is computed only when the task's expected_output includes an
        error_handling field. The score is reported alongside primary metrics
        but does NOT override them.

        Args:
            response: The agent's output text.
            expected_behavior: Dict with error_handling expectations:
                - error_type: Category of error
                - should_report_error: Whether agent should mention an error
                - should_retry: Whether agent should attempt retry
                - expected_behavior: Description of ideal behavior

        Returns:
            Dict with error handling evaluation metrics.
        """
        response_lower = response.lower() if response else ""

        # Check if agent reported an error
        error_indicators = [
            "error",
            "failed",
            "unavailable",
            "issue",
            "problem",
            "500",
            "503",
            "429",
            "404",
            "rate limit",
            "service",
            "maintenance",
            "temporarily",
            "server error",
        ]
        error_reported = any(
            indicator in response_lower for indicator in error_indicators
        )

        # Check if agent mentioned retry
        retry_indicators = [
            "retry",
            "retried",
            "try again",
            "attempted again",
            "re-attempted",
        ]
        retry_mentioned = any(
            indicator in response_lower for indicator in retry_indicators
        )

        # Check for graceful degradation (agent provided useful info despite error)
        has_content = len(response_lower) > 50 and not response_lower.startswith(
            "error:"
        )
        graceful = has_content

        # Compute score
        score_parts = []
        should_report = expected_behavior.get("should_report_error", False)
        should_retry = expected_behavior.get("should_retry", False)

        if should_report:
            score_parts.append(1.0 if error_reported else 0.0)
        else:
            # Should NOT report error — penalize if it did
            score_parts.append(0.5 if error_reported else 1.0)

        if should_retry:
            score_parts.append(1.0 if retry_mentioned else 0.0)

        score_parts.append(1.0 if graceful else 0.0)

        error_handling_score = (
            sum(score_parts) / len(score_parts) if score_parts else 0.0
        )

        return {
            "error_type": expected_behavior.get("error_type", "unknown"),
            "error_reported": error_reported,
            "retry_attempted": retry_mentioned,
            "graceful_degradation": graceful,
            "error_handling_score": round(error_handling_score, 2),
        }

    @staticmethod
    def final_task_score(
        output_exact_match: int,
        output_similarity: float,
        llm_judge_score: Any,
        llm_judge_requested: bool,
        agent_output: str,
        threshold_exact: float = 0.85,
        threshold_inexact: float = 0.9,
        apis_missing: List[str] = None,
        require_api_match: bool = False,
    ) -> int:
        """
        Compute the final binary score for a task.

        This is a composite metric that determines if a task response is acceptable
        based on exact match status, similarity, and optionally LLM judge score.

        Logic:
        - If output_exact_match == 1: pass if EITHER llm_judge_score or output_similarity
          is >= threshold_exact (default 0.85).
        - If output_exact_match == 0: pass if EITHER llm_judge_score or output_similarity
          is >= threshold_inexact (default 0.9).
        - If LLM judge was NOT requested (llm_judge_requested=False), only output_similarity
          is considered.
        - If LLM judge WAS requested but failed (llm_judge_score is None), return 0
          (do not fall back to similarity-only).
        - If the task obviously failed (agent_output starts with "ERROR:"), return 0.
        - If require_api_match is True and apis_missing is non-empty, return 0.

        Args:
            output_exact_match: 1 if exact match, 0 otherwise.
            output_similarity: String similarity score (0.0 to 1.0).
            llm_judge_score: LLM judge score (float 0.0-1.0) or None if not available.
            llm_judge_requested: True if an LLM judge was requested for this evaluation run.
            agent_output: The agent's output string (to detect failures).
            threshold_exact: Threshold when exact match is True (default 0.85).
            threshold_inexact: Threshold when exact match is False (default 0.9).
            apis_missing: List of expected APIs that were not called.
            require_api_match: If True, require apis_missing to be empty to pass.

        Returns:
            1 if the task passes, 0 otherwise.
        """
        import math

        # Check for task failure indicators
        if not agent_output or (
            isinstance(agent_output, str) and agent_output.startswith("ERROR:")
        ):
            return 0

        # Check for missing API calls when API metrics are required
        if require_api_match and apis_missing:
            return 0

        # Handle missing/invalid similarity
        if output_similarity is None or (
            isinstance(output_similarity, float) and math.isnan(output_similarity)
        ):
            return 0

        # Determine the threshold based on exact match status
        threshold = threshold_exact if output_exact_match == 1 else threshold_inexact

        # Check if LLM judge score is available
        judge_available = False
        judge_score = 0.0
        if llm_judge_requested and llm_judge_score is not None:
            if not (isinstance(llm_judge_score, float) and math.isnan(llm_judge_score)):
                judge_available = True
                judge_score = float(llm_judge_score)

        # Determine pass/fail based on available metrics
        if judge_available:
            # Judge available: pass if EITHER score meets threshold
            if judge_score >= threshold or output_similarity >= threshold:
                return 1
            return 0
        else:
            # Judge not available or not requested: use similarity only
            if output_similarity >= threshold:
                return 1
            return 0

    @staticmethod
    def aggregate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate evaluation results across multiple tasks.

        Args:
            results: List of individual task evaluation results.

        Returns:
            Aggregated metrics.
        """
        total = len(results)
        if total == 0:
            return {
                "total_tasks": 0,
                "exact_matches": 0,
                "accuracy": 0,
                "avg_similarity": 0,
                "api_accuracy": 0,
                "api_count_accuracy": 0,
                "avg_keyword_match_ratio": 0,
                "keyword_full_matches": 0,
                "llm_judged_tasks": 0,
                "avg_llm_judge_score": None,
                "llm_judge_binary_accuracy": None,
                "final_score_passes": 0,
                "final_score_accuracy": 0,
            }

        # All binary metrics are now 0/1 integers for consistency
        exact_matches = sum(r.get("output_exact_match", 0) for r in results)
        total_similarity = sum(r.get("output_similarity", 0) for r in results)
        api_correct = sum(r.get("apis_correct", 0) for r in results)
        api_count_correct = sum(r.get("api_count_correct", 0) for r in results)

        # LLM judge metrics (optional)
        llm_scored = [r for r in results if r.get("llm_judge_score") is not None]
        if llm_scored:
            avg_llm_judge_score = sum(
                float(r["llm_judge_score"]) for r in llm_scored
            ) / len(llm_scored)
        else:
            avg_llm_judge_score = None

        # LLM judge binary metric (threshold 0.5 by default)
        llm_binary_scored = [
            r for r in results if r.get("llm_judge_binary") is not None
        ]
        if llm_binary_scored:
            binary_matches = sum(
                1 for r in llm_binary_scored if r["llm_judge_binary"] == 1
            )
            llm_judge_binary_accuracy = binary_matches / len(llm_binary_scored)
        else:
            llm_judge_binary_accuracy = None

        # Keyword metrics (only for tasks that have keywords defined)
        tasks_with_keywords = [r for r in results if r.get("keywords_total", 0) > 0]
        if tasks_with_keywords:
            avg_keyword_ratio = sum(
                r.get("keywords_match_ratio", 0) for r in tasks_with_keywords
            ) / len(tasks_with_keywords)
            keyword_full_matches = sum(
                1
                for r in tasks_with_keywords
                if r.get("keywords_match_ratio", 0) == 1.0
            )
        else:
            avg_keyword_ratio = 1.0  # No keywords defined = perfect match
            keyword_full_matches = 0

        # Final score metrics (task_final_score is 0 or 1 for each task)
        final_score_passes = sum(r.get("task_final_score", 0) for r in results)
        final_score_accuracy = final_score_passes / total

        # Langfuse usage metrics (from metadata)
        langfuse_metrics = EvaluationMetrics._aggregate_langfuse_metrics(results)

        return {
            "total_tasks": total,
            "exact_matches": exact_matches,
            "accuracy": exact_matches / total,
            "avg_similarity": total_similarity / total,
            "api_accuracy": api_correct / total,
            "api_count_accuracy": api_count_correct / total,
            "avg_keyword_match_ratio": avg_keyword_ratio,
            "keyword_full_matches": keyword_full_matches,
            "tasks_with_keywords": len(tasks_with_keywords),
            "llm_judged_tasks": len(llm_scored),
            "avg_llm_judge_score": avg_llm_judge_score,
            "llm_judge_binary_accuracy": llm_judge_binary_accuracy,
            "final_score_passes": final_score_passes,
            "final_score_accuracy": final_score_accuracy,
            **langfuse_metrics,
        }

    @staticmethod
    def _aggregate_langfuse_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate Langfuse usage metrics from task results.

        Extracts total_llm_calls, total_tokens, total_cost, and
        total_cache_input_tokens from each task's metadata.

        Args:
            results: List of individual task evaluation results.

        Returns:
            Aggregated Langfuse metrics dict.
        """
        total_llm_calls = 0
        total_tokens = 0
        total_cost = 0.0
        total_cache_input_tokens = 0
        tasks_with_langfuse = 0

        for r in results:
            metadata = r.get("metadata", {}) or {}
            if "total_llm_calls" in metadata:
                tasks_with_langfuse += 1
                total_llm_calls += metadata.get("total_llm_calls", 0) or 0
                total_tokens += metadata.get("total_tokens", 0) or 0
                total_cost += metadata.get("total_cost", 0.0) or 0.0
                total_cache_input_tokens += (
                    metadata.get("total_cache_input_tokens", 0) or 0
                )

        if tasks_with_langfuse == 0:
            return {}

        return {
            "langfuse_tasks_tracked": tasks_with_langfuse,
            "total_llm_calls": total_llm_calls,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "total_cache_input_tokens": total_cache_input_tokens,
            "avg_llm_calls_per_task": round(total_llm_calls / tasks_with_langfuse, 2),
            "avg_tokens_per_task": round(total_tokens / tasks_with_langfuse, 2),
            "avg_cost_per_task": round(total_cost / tasks_with_langfuse, 6),
        }

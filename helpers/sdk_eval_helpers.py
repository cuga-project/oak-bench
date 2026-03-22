"""Helper functions for SDK evaluation benchmarks.

This module provides reusable functions for:
- Agent setup with tools and Langfuse
- Policy management
- Keyword checking
- Task evaluation with Langfuse tracing
- Multi-turn task evaluation
- Summary printing
- Tracker callbacks

Enhanced metrics (opt-in via metrics_config):
- String similarity scoring
- LLM judge semantic evaluation
- Final score calculation
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, TypedDict
from loguru import logger


class MetricsConfig(TypedDict, total=False):
    """Configuration for enhanced evaluation metrics.

    All fields are optional. When metrics_config is not provided or empty,
    only keyword matching is performed (default behavior for backwards compatibility).

    Fields:
        enable_similarity: Compute string similarity score (0.0-1.0)
        enable_llm_judge: Run LLM judge for semantic evaluation
        llm_judge_provider: LLM judge provider ("groq", "mock", etc.)
        expected_output_key: Key path to expected output in task dict (default: "expected_output.answer")
        final_score_threshold_exact: Threshold when exact match (default: 0.85)
        final_score_threshold_inexact: Threshold when no exact match (default: 0.9)
        similarity_method: Method for string similarity (default: "rapidfuzz_token_set")
    """

    enable_similarity: bool
    enable_llm_judge: bool
    enable_api_metrics: bool
    llm_judge_provider: str
    expected_output_key: str
    final_score_threshold_exact: float
    final_score_threshold_inexact: float
    similarity_method: str


class TokenUsageCallback:
    """Resettable callback that accumulates LLM token usage per task.

    Attach once at agent creation via extra_callbacks; call reset() before each
    task so counts reflect only that task's invoke.

    Wraps a real LangChain BaseCallbackHandler so LangGraph sees all required
    attributes (run_inline, ignore_llm, etc.).
    """

    def __init__(self):
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        # Build the inner LangChain handler lazily so the import happens at
        # runtime (after env vars are set) rather than at module load time.
        self._handler = None

    def _ensure_handler(self):
        if self._handler is not None:
            return self._handler
        from langchain_core.callbacks import BaseCallbackHandler

        outer = self

        class _Inner(BaseCallbackHandler):
            def on_llm_end(self, response, **kwargs):
                if not response.llm_output:
                    return
                out = response.llm_output
                # Anthropic format
                usage = out.get("usage", {}) or {}
                outer.input_tokens += usage.get("input_tokens", 0)
                outer.output_tokens += usage.get("output_tokens", 0)
                # OpenAI format
                token_usage = out.get("token_usage", {}) or {}
                outer.input_tokens += token_usage.get("prompt_tokens", 0)
                outer.output_tokens += token_usage.get("completion_tokens", 0)

        self._handler = _Inner()
        return self._handler

    # ── Proxy every attribute LangChain/LangGraph expects to the inner handler ──
    def __getattr__(self, name: str):
        # Called only when the attribute isn't found on TokenUsageCallback itself
        return getattr(self._ensure_handler(), name)

    def reset(self):
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _std(values: List[float]) -> float:
    """Population std-dev (ddof=1 when n>1, else 0)."""
    n = len(values)
    if n < 2:
        return 0.0
    m = sum(values) / n
    return (sum((x - m) ** 2 for x in values) / (n - 1)) ** 0.5


def _lcs_length(seq1: List[str], seq2: List[str]) -> int:
    """Longest common subsequence length (used for tool-call order scoring)."""
    m, n = len(seq1), len(seq2)
    # Space-optimised DP: only two rows needed
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


# Lazy-loaded modules for enhanced metrics
_metrics_module = None
_llm_judge_module = None


def _get_metrics_class():
    """Lazy import of EvaluationMetrics."""
    global _metrics_module
    if _metrics_module is None:
        try:
            from helpers.metrics import EvaluationMetrics

            _metrics_module = EvaluationMetrics
        except ImportError:
            logger.warning(
                "helpers.metrics not available - similarity metrics disabled"
            )
            _metrics_module = False
    return _metrics_module if _metrics_module else None


def _get_llm_judge(provider: str, **kwargs):
    """Lazy import and creation of LLM judge."""
    global _llm_judge_module
    if _llm_judge_module is None:
        try:
            from bpo import llm_judge as ljm

            _llm_judge_module = ljm
        except ImportError:
            logger.warning("bpo.llm_judge not available - LLM judge disabled")
            _llm_judge_module = False

    if _llm_judge_module:
        try:
            return _llm_judge_module.get_llm_judge(provider, **kwargs)
        except Exception as e:
            logger.warning(f"Failed to create LLM judge: {e}")
    return None


def _get_nested_value(d: Dict, key_path: str, default=None):
    """Get a nested value from a dict using dot notation."""
    keys = key_path.split(".")
    value = d
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def _extract_tool_calls_from_tracker() -> List[Dict[str, Any]]:
    """Extract tool calls from ActivityTracker.steps.

    This is the standard approach used by oak_health_insurance and cuga evaluate.
    Tool calls are recorded as steps with "api_call" in the name.

    Returns:
        List of tool call dicts with 'name' and 'args' keys
    """
    from cuga.backend.activity_tracker.tracker import ActivityTracker

    tracker = ActivityTracker()  # Singleton - returns existing instance
    tool_calls = []

    # Debug: log step names to understand what's being tracked
    logger.info(f"[TOOL_TRACKING] ActivityTracker has {len(tracker.steps)} steps")
    if tracker.steps:
        step_names = [s.name for s in tracker.steps[:10]]
        logger.info(f"[TOOL_TRACKING] First step names: {step_names}")

    for step in tracker.steps:
        if step.name and "api_call" in step.name:
            try:
                call_data = json.loads(step.data) if step.data else {}
                tool_calls.append(
                    {
                        "name": call_data.get("function_name", ""),
                        "args": call_data.get("args", {}),
                    }
                )
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse tool call step data: {e}")
                continue

    return tool_calls


from cuga.sdk import CugaAgent
from cuga.backend.cuga_graph.nodes.cuga_lite.combined_tool_provider import (
    CombinedToolProvider,
)
from cuga.backend.cuga_graph.policy.models import PolicyType
from langchain_core.messages import HumanMessage


async def setup_agent_with_tools(
    special_instructions: Optional[str] = None,
    extra_callbacks: Optional[List[Any]] = None,
) -> tuple[CugaAgent, Optional[Any]]:
    """Set up CugaAgent with tools and Langfuse tracing.

    Args:
        special_instructions: Optional special instructions to pass to the agent
        extra_callbacks: Optional additional LangChain callbacks (e.g. TokenUsageCallback)

    Returns:
        Tuple of (agent, langfuse_handler)
    """
    logger.info("Setting up evaluator...")

    tool_provider = CombinedToolProvider()
    await tool_provider.initialize()
    all_tools = await tool_provider.get_all_tools()
    logger.info(f"Loaded {len(all_tools)} tools")

    langfuse_handler = setup_langfuse()
    callbacks = [langfuse_handler] if langfuse_handler else []
    if langfuse_handler:
        logger.info("✅ Langfuse tracing enabled")
        logger.info(f"   Callback handler type: {type(langfuse_handler).__name__}")
    else:
        logger.info("ℹ️  Langfuse not available (optional)")

    if extra_callbacks:
        callbacks = callbacks + extra_callbacks

    agent_kwargs = {"tool_provider": tool_provider, "callbacks": callbacks}
    if special_instructions:
        agent_kwargs["special_instructions"] = special_instructions
        logger.info("   Special instructions provided")

    agent = CugaAgent(**agent_kwargs)
    logger.info(f"   Agent created with {len(callbacks)} callback(s)")

    return agent, langfuse_handler


def setup_langfuse():
    """Setup Langfuse tracing callback handler.

    Returns:
        Langfuse callback handler if available, None otherwise
    """
    try:
        from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
    except ImportError:
        try:
            from langfuse.callback.langchain import (
                LangchainCallbackHandler as LangfuseCallbackHandler,
            )
        except ImportError:
            logger.warning(
                "Langfuse package not installed. Install with: pip install langfuse"
            )
            return None

    try:
        handler = LangfuseCallbackHandler()
        return handler
    except Exception as e:
        logger.error(f"Failed to create Langfuse handler: {e}")
        import traceback

        logger.debug(traceback.format_exc())
        return None


async def clear_all_policies(agent: CugaAgent):
    """Clear all existing policies from the database."""
    try:
        existing_policies = await agent.policies.list()
        if existing_policies:
            logger.info(
                f"Found {len(existing_policies)} existing policies, deleting..."
            )
            for policy in existing_policies:
                await agent.policies.delete(policy["id"])
            logger.info(f"✅ Cleared {len(existing_policies)} existing policies")
        else:
            logger.info("No existing policies to clear")
    except Exception as e:
        logger.warning(f"Failed to clear existing policies: {e}")


async def add_policy_via_agent(agent: CugaAgent, policy):
    """Add a policy using the agent's public API methods.

    Args:
        agent: CugaAgent instance
        policy: Policy object (Playbook, ToolGuide, etc.)
    """
    policy_type = policy.policy_type if hasattr(policy, "policy_type") else policy.type

    if policy_type == PolicyType.PLAYBOOK:
        keywords = []
        natural_language_trigger = []
        threshold = 0.7

        for trigger in policy.triggers:
            trigger_type = getattr(trigger, "type", None)
            if trigger_type == "keyword":
                trigger_value = getattr(trigger, "value", [])
                if isinstance(trigger_value, list):
                    keywords.extend(trigger_value)
                else:
                    keywords.append(trigger_value)
            elif trigger_type == "natural_language":
                trigger_value = getattr(trigger, "value", [])
                if isinstance(trigger_value, list):
                    natural_language_trigger.extend(trigger_value)
                else:
                    natural_language_trigger.append(trigger_value)
                threshold = getattr(trigger, "threshold", 0.7)

        await agent.policies.add_playbook(
            name=policy.name,
            content=policy.markdown_content,
            description=policy.description,
            keywords=keywords if keywords else None,
            natural_language_trigger=natural_language_trigger
            if natural_language_trigger
            else None,
            threshold=threshold,
            priority=policy.priority,
            enabled=policy.enabled,
            policy_id=policy.id,
        )

    elif policy_type == PolicyType.TOOL_GUIDE:
        keywords = []

        for trigger in policy.triggers:
            trigger_type = getattr(trigger, "type", None)
            if trigger_type == "keyword":
                trigger_value = getattr(trigger, "value", [])
                if isinstance(trigger_value, list):
                    keywords.extend(trigger_value)
                else:
                    keywords.append(trigger_value)

        await agent.policies.add_tool_guide(
            name=policy.name,
            content=policy.guide_content,
            target_tools=policy.target_tools,
            description=policy.description,
            keywords=keywords if keywords else None,
            target_apps=getattr(policy, "target_apps", None),
            prepend=getattr(policy, "prepend", False),
            priority=policy.priority,
            enabled=policy.enabled,
            policy_id=policy.id,
        )

    else:
        policy_system = await agent.policies._ensure_policy_system()
        await policy_system.storage.add_policy(policy)
        await policy_system.initialize()


def create_activity_tracker_callback(
    tracker, var_manager=None
) -> Callable[[Dict[str, Any], Dict[str, Any], str], None]:
    """Create a tracker callback function for ActivityTracker.

    Args:
        tracker: ActivityTracker instance
        var_manager: Optional VariablesManager instance to reset

    Returns:
        Callback function that can be passed to evaluate_task_with_langfuse
    """

    def tracker_callback(
        result: Dict[str, Any], keyword_check: Dict[str, Any], intent: str
    ):
        """Callback for tracking evaluation results with ActivityTracker."""
        from cuga.backend.activity_tracker.tracker import Step

        task_name = result["task_name"]
        response = result.get("response", "")

        if result.get("error"):
            error_report = json.dumps(
                {
                    "task_name": task_name,
                    "difficulty": result.get("difficulty", "unknown"),
                    "success": False,
                    "error": result["error"],
                }
            )
            tracker.finish_task(
                intent=intent,
                site="",
                task_id=task_name,
                eval=error_report,
                score=0.0,
                agent_answer="",
                exception=True,
                num_steps=0,
                total_llm_calls=0,
                total_tokens=0,
                total_cost=0.0,
                agent_v="",
            )
            tracker.collect_score(0.0)
        else:
            report_md = json.dumps(
                {
                    "task_name": task_name,
                    "difficulty": result.get("difficulty", "unknown"),
                    "success": result["success"],
                    "match_rate": keyword_check["match_rate"],
                    "found_keywords": keyword_check["found_keywords"],
                    "missing_keywords": keyword_check["missing_keywords"],
                }
            )
            score = keyword_check["match_rate"]
            tracker.finish_task(
                intent=intent,
                site="",
                task_id=task_name,
                eval=report_md,
                score=score,
                agent_answer=response,
                exception=False,
                num_steps=0,
                total_llm_calls=0,
                total_tokens=0,
                total_cost=0.0,
                agent_v="",
            )
            tracker.collect_step(Step(name="EvaluationResult", data=report_md))
            tracker.collect_score(score)

    return tracker_callback


def check_keywords(response: str, expected_keywords: List[str]) -> Dict[str, Any]:
    """Check if expected keywords are present in the response.

    Supports OR mechanism: keywords can use "|" to specify alternatives.
    Example: "1000|1,000" will match if either "1000" or "1,000" is found.

    Args:
        response: Agent's response text
        expected_keywords: List of keywords that should be present (can use "|" for OR)

    Returns:
        Dictionary with keyword check results
    """
    answer_str = (
        response.replace("\u202f", " ")
        .replace("\u00a0", " ")
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    response_lower = answer_str.lower()
    found_keywords = []
    missing_keywords = []

    for keyword in expected_keywords:
        if "|" in keyword:
            alternatives = [alt.strip() for alt in keyword.split("|")]
            matched = False
            for alt in alternatives:
                alt_lower = alt.lower()
                if alt_lower in response_lower:
                    matched = True
                    break

            if matched:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)
        else:
            keyword_lower = keyword.lower()
            if keyword_lower in response_lower:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    all_found = len(missing_keywords) == 0
    match_rate = (
        len(found_keywords) / len(expected_keywords) if expected_keywords else 0.0
    )

    return {
        "all_found": all_found,
        "match_rate": match_rate,
        "found_keywords": found_keywords,
        "missing_keywords": missing_keywords,
        "total_keywords": len(expected_keywords),
        "found_count": len(found_keywords),
    }


async def evaluate_task_with_langfuse(
    agent: CugaAgent,
    task: Dict[str, Any],
    task_index: int,
    langfuse_handler: Optional[Any] = None,
    user_context: Optional[str] = None,
    tracker_callback: Optional[
        Callable[[Dict[str, Any], Dict[str, Any], str], None]
    ] = None,
    track_tool_calls: bool = True,
    metrics_config: Optional[MetricsConfig] = None,
    token_callback: Optional["TokenUsageCallback"] = None,
) -> Dict[str, Any]:
    """Evaluate a single task with optional Langfuse tracing and enhanced metrics.

    Args:
        agent: CugaAgent instance
        task: Task dictionary with 'name', 'intent', 'difficulty', 'expected_output'
        task_index: Index of the task (for unique thread_id generation)
        langfuse_handler: Optional Langfuse handler for tracing
        user_context: Optional user context string
        tracker_callback: Optional callback function for tracking (receives result dict, keyword_check dict, intent string)
        track_tool_calls: Whether to track tool calls (default: True)
        metrics_config: Optional configuration for enhanced metrics (similarity, LLM judge, final score).
                       When None, only keyword matching is performed (backwards compatible).

    Returns:
        Evaluation result dictionary with:
        - Basic fields: task_name, difficulty, intent, thread_id, success, match_rate, response, etc.
        - Enhanced fields (when metrics_config provided): output_similarity, output_exact_match,
          llm_judge_score, llm_judge_binary, llm_judge_rationale, task_final_score
    """
    task_name = task.get("name", "unknown")
    intent = task.get("intent", "")
    difficulty = task.get("difficulty", "unknown")
    expected_output = task.get("expected_output", {})
    expected_keywords = expected_output.get("keywords", [])

    thread_id = f"eval_{task_name}_{task_index}_{uuid.uuid4().hex[:8]}"

    logger.info(f"\n{'=' * 80}")
    logger.info(f"Evaluating: {task_name} ({difficulty})")
    logger.info(f"Thread ID: {thread_id}")
    logger.info(f"Intent: {intent}")
    logger.info(f"Expected keywords: {expected_keywords}")
    logger.info(f"{'=' * 80}")

    try:
        keyword_check_result = None
        tool_calls = []

        if token_callback:
            token_callback.reset()
        _task_start = time.monotonic()

        if langfuse_handler:
            try:
                from langfuse import get_client

                langfuse = get_client()

                trace_name = f"eval_{task_name}_{task_index}"
                predefined_trace_id = langfuse.create_trace_id(
                    seed=f"{task_name}_{task_index}_{thread_id}"
                )

                logger.info(
                    f"📊 Starting Langfuse trace: {trace_name} (ID: {predefined_trace_id})"
                )

                with langfuse.start_as_current_observation(
                    as_type="span",
                    name=trace_name,
                    trace_context={"trace_id": predefined_trace_id},
                    input={
                        "intent": intent,
                        "task_name": task_name,
                        "difficulty": difficulty,
                        "expected_keywords": expected_keywords,
                    },
                    metadata={"thread_id": thread_id, "task_index": task_index},
                ) as span:
                    invoke_result = await agent.invoke(
                        [HumanMessage(content=intent)],
                        thread_id=thread_id,
                        user_context=user_context or "",
                        track_tool_calls=track_tool_calls,
                    )
                    # Handle both string and object return types
                    result_state = (
                        invoke_result.answer
                        if hasattr(invoke_result, "answer")
                        else invoke_result
                    )

                    keyword_check = check_keywords(result_state, expected_keywords)

                    response_preview = result_state
                    span.update(
                        output={
                            "response_preview": response_preview,
                            "keyword_results": {
                                "found_keywords": keyword_check["found_keywords"],
                                "missing_keywords": keyword_check["missing_keywords"],
                                "total_keywords": keyword_check["total_keywords"],
                                "found_count": keyword_check["found_count"],
                            },
                        },
                        metadata={
                            "thread_id": thread_id,
                            "task_index": task_index,
                        },
                    )

                    missing_keywords_str = (
                        ", ".join(keyword_check["missing_keywords"])
                        if keyword_check["missing_keywords"]
                        else "none"
                    )
                    span.score_trace(
                        name="keyword_match",
                        value=keyword_check["match_rate"],
                        data_type="NUMERIC",
                        comment=f"Keyword match rate: {keyword_check['found_count']}/{keyword_check['total_keywords']} keywords found. Missing keywords: {missing_keywords_str}",
                    )

                    overall_score = True if keyword_check["all_found"] else False
                    span.score_trace(
                        name="success",
                        value=overall_score,
                        data_type="BOOLEAN",
                        comment="Overall task success: True if all keywords found, otherwise False",
                    )

                response = result_state
                keyword_check_result = keyword_check
            except Exception as e:
                logger.warning(f"Failed to start Langfuse trace: {e}")
                invoke_result = await agent.invoke(
                    [HumanMessage(content=intent)],
                    thread_id=thread_id,
                    user_context=user_context or "",
                    track_tool_calls=track_tool_calls,
                )
                # Handle both string and object return types
                response = (
                    invoke_result.answer
                    if hasattr(invoke_result, "answer")
                    else invoke_result
                )
                keyword_check_result = check_keywords(response, expected_keywords)
        else:
            invoke_result = await agent.invoke(
                [HumanMessage(content=intent)],
                thread_id=thread_id,
                user_context=user_context or "",
                track_tool_calls=track_tool_calls,
            )
            # Handle both string and object return types
            response = (
                invoke_result.answer
                if hasattr(invoke_result, "answer")
                else invoke_result
            )
            keyword_check_result = check_keywords(response, expected_keywords)

        _latency = round(time.monotonic() - _task_start, 2)

        if keyword_check_result is None:
            keyword_check = check_keywords(response, expected_keywords)
        else:
            keyword_check = keyword_check_result

        # Extract tool calls from ActivityTracker.steps (same approach as oak and cuga evaluate)
        if track_tool_calls:
            tool_calls = _extract_tool_calls_from_tracker()
            logger.info(
                f"[TOOL_TRACKING] Extracted {len(tool_calls)} tool calls from ActivityTracker"
            )

            # Fallback: if ActivityTracker didn't capture tool calls, try invoke_result.tool_calls
            if (
                not tool_calls
                and hasattr(invoke_result, "tool_calls")
                and invoke_result.tool_calls
            ):
                logger.info("[TOOL_TRACKING] Falling back to invoke_result.tool_calls")
                for tc in invoke_result.tool_calls:
                    if isinstance(tc, dict):
                        tool_calls.append(
                            {"name": tc.get("name", ""), "args": tc.get("args", {})}
                        )
                    elif hasattr(tc, "name"):
                        tool_calls.append(
                            {"name": tc.name, "args": getattr(tc, "args", {})}
                        )
                    elif hasattr(tc, "model_dump"):
                        tc_dict = tc.model_dump()
                        tool_calls.append(
                            {
                                "name": tc_dict.get("name", ""),
                                "args": tc_dict.get("args", {}),
                            }
                        )
                logger.info(
                    f"[TOOL_TRACKING] Extracted {len(tool_calls)} tool calls from invoke_result"
                )
        else:
            tool_calls = []

        # Build base result (backwards compatible)
        result = {
            "task_name": task_name,
            "difficulty": difficulty,
            "intent": intent,
            "thread_id": thread_id,
            "success": keyword_check["all_found"],
            "match_rate": keyword_check["match_rate"],
            "response": response,
            "expected_keywords": expected_keywords,
            "found_keywords": keyword_check["found_keywords"],
            "missing_keywords": keyword_check["missing_keywords"],
            "tool_calls": [tc for tc in tool_calls] if tool_calls else [],
            "latency_seconds": _latency,
            "tokens_input": token_callback.input_tokens if token_callback else None,
            "tokens_output": token_callback.output_tokens if token_callback else None,
            "tokens_total": token_callback.total_tokens if token_callback else None,
            "error": None,
        }

        # Compute enhanced metrics if metrics_config is provided
        if metrics_config:
            # Get expected output for comparison
            expected_output_key = metrics_config.get(
                "expected_output_key", "expected_output.answer"
            )
            expected_answer = _get_nested_value(task, expected_output_key)
            if expected_answer is None:
                # Fallback: try common patterns
                expected_answer = (
                    task.get("expected_output", {}).get("answer")
                    or task.get("expected_output", {}).get("text")
                    or task.get("expected_answer")
                    or str(task.get("expected_output", ""))
                )

            result["expected_answer"] = expected_answer

            # Similarity metrics
            if metrics_config.get("enable_similarity", False):
                MetricsClass = _get_metrics_class()
                if MetricsClass:
                    method = metrics_config.get(
                        "similarity_method", "rapidfuzz_token_set"
                    )
                    try:
                        similarity = MetricsClass.string_similarity(
                            response, expected_answer, method=method
                        )
                        exact_match = MetricsClass.exact_match(
                            response, expected_answer
                        )
                        result["output_similarity"] = similarity
                        result["output_exact_match"] = 1 if exact_match else 0
                    except Exception as e:
                        logger.warning(f"Failed to compute similarity: {e}")
                        result["output_similarity"] = None
                        result["output_exact_match"] = None

            # LLM Judge metrics
            if metrics_config.get("enable_llm_judge", False):
                provider = metrics_config.get("llm_judge_provider", "groq")
                judge = _get_llm_judge(provider)
                if judge:
                    try:
                        judge_result = await judge.judge(
                            predicted=response,
                            expected=expected_answer,
                            task_context={"utterance": intent, "task_id": task_name},
                        )
                        llm_score = judge_result.get("score")
                        result["llm_judge_score"] = llm_score
                        result["llm_judge_binary"] = (
                            1 if llm_score and llm_score >= 0.5 else 0
                        )
                        result["llm_judge_rationale"] = judge_result.get(
                            "rationale", ""
                        )[:200]
                        result["llm_judge_name"] = judge.name
                    except Exception as e:
                        logger.warning(f"LLM judge failed: {e}")
                        result["llm_judge_score"] = None
                        result["llm_judge_binary"] = None
                        result["llm_judge_rationale"] = f"Error: {e}"
                        result["llm_judge_name"] = None

            # API call metrics
            if metrics_config.get("enable_api_metrics", False):
                # Get expected tool calls from task
                expected_tool_calls = task.get("expected_output", {}).get(
                    "tool_calls", []
                )
                expected_api_names = set()
                for tc in expected_tool_calls:
                    if isinstance(tc, dict) and "name" in tc:
                        expected_api_names.add(tc["name"])
                    elif isinstance(tc, str):
                        expected_api_names.add(tc)

                # Get actual tool calls from agent response
                actual_api_names = set()
                for tc in tool_calls:
                    if hasattr(tc, "name"):
                        actual_api_names.add(tc.name)
                    elif isinstance(tc, dict) and "name" in tc:
                        actual_api_names.add(tc["name"])
                    elif isinstance(tc, str):
                        actual_api_names.add(tc)

                # Normalize API names for comparison
                # Registry tool names are verbose: bpo_candidate_source_sla_per_source_candidate_source_sla_per_source_requisition_id_get
                # Expected names are short: candidate_source_sla_per_source
                def normalize_api_name(name: str) -> str:
                    name = name.lower().strip()
                    # Remove app prefix
                    if name.startswith("bpo_"):
                        name = name[4:]
                    # Remove common suffixes (HTTP methods and parameter patterns)
                    for suffix in ["_get", "_post", "_put", "_delete"]:
                        if name.endswith(suffix):
                            name = name[: -len(suffix)]
                    for suffix in ["_requisition_id", "_skill_name"]:
                        if name.endswith(suffix):
                            name = name[: -len(suffix)]
                    return name.replace("-", "_").replace(" ", "_")

                def api_matches(expected: str, actual: str) -> bool:
                    """Check if expected API name matches actual (allowing for verbose registry names).

                    Handles two mismatches:
                    - ActivityTracker stores short names: oak_health_get_member
                    - Test suites store verbose registry names: oak_health_get_member_get_member_post
                    Both directions are checked using prefix matching (word boundary via '_').
                    """
                    exp_norm = normalize_api_name(expected)
                    act_norm = normalize_api_name(actual)
                    # Direct match
                    if exp_norm == act_norm:
                        return True
                    # Actual short name is a prefix of verbose expected (main case):
                    # "oak_health_get_member" matches "oak_health_get_member_get_member"
                    if exp_norm.startswith(act_norm + "_"):
                        return True
                    # Expected short name is a prefix of verbose actual (reverse case)
                    if act_norm.startswith(exp_norm + "_"):
                        return True
                    return False

                logger.info(f"[API_TRACKING] Expected APIs: {list(expected_api_names)}")
                logger.info(f"[API_TRACKING] Actual APIs: {list(actual_api_names)}")

                # Compute API metrics using flexible matching
                apis_missing = []
                for exp_api in expected_api_names:
                    if not any(
                        api_matches(exp_api, act_api) for act_api in actual_api_names
                    ):
                        apis_missing.append(exp_api)

                apis_extra = []
                for act_api in actual_api_names:
                    if not any(
                        api_matches(exp_api, act_api) for exp_api in expected_api_names
                    ):
                        apis_extra.append(act_api)

                apis_correct = len(apis_missing) == 0

                result["expected_apis"] = list(expected_api_names)
                result["apis_called"] = list(actual_api_names)
                result["apis_missing"] = apis_missing
                result["apis_extra"] = apis_extra
                result["apis_correct"] = 1 if apis_correct else 0
                result["api_call_count"] = len(tool_calls)
                result["expected_api_count"] = len(expected_tool_calls)
                result["api_count_correct"] = 1 if len(apis_missing) == 0 else 0

                # Derived summary metrics — multiset (greedy) matching
                # Each actual call can only satisfy one expected call (duplicates matter)
                result["tool_call_count"] = len(tool_calls)
                exp_list = [
                    tc["name"] if isinstance(tc, dict) else tc
                    for tc in expected_tool_calls
                ]
                act_available = [
                    tc["name"]
                    for tc in tool_calls
                    if isinstance(tc, dict) and tc.get("name")
                ]
                tp = 0
                for exp_name in exp_list:
                    for idx, act_name in enumerate(act_available):
                        if api_matches(exp_name, act_name):
                            tp += 1
                            act_available.pop(idx)
                            break

                n_actual_total = len(tool_calls)
                n_expected_total = len(exp_list)
                recall = (
                    round(tp / n_expected_total, 3) if n_expected_total > 0 else 1.0
                )
                precision = (
                    round(tp / n_actual_total, 3)
                    if n_actual_total > 0
                    else (1.0 if n_expected_total == 0 else 0.0)
                )
                f1 = (
                    round(2 * precision * recall / (precision + recall), 3)
                    if (precision + recall) > 0
                    else 0.0
                )

                result["tool_call_recall"] = recall
                result["tool_call_precision"] = precision
                result["tool_call_f1"] = f1

                # Order score: LCS of expected vs actual call sequences (normalized names)
                # Captures whether the right tools were called in the right order
                exp_seq = [
                    normalize_api_name(tc["name"])
                    for tc in expected_tool_calls
                    if isinstance(tc, dict)
                ]
                act_seq = [
                    normalize_api_name(tc["name"])
                    for tc in tool_calls
                    if isinstance(tc, dict) and tc.get("name")
                ]
                if exp_seq:
                    lcs_len = _lcs_length(exp_seq, act_seq)
                    result["tool_call_order_score"] = round(lcs_len / len(exp_seq), 3)
                else:
                    result["tool_call_order_score"] = 1.0

                # Ground truth counts (from benchmark definition)
                result["expected_tool_call_count"] = len(expected_tool_calls)

            # Final score (composite metric)
            if metrics_config.get("enable_similarity", False) or metrics_config.get(
                "enable_llm_judge", False
            ):
                MetricsClass = _get_metrics_class()
                if MetricsClass and result.get("output_similarity") is not None:
                    try:
                        threshold_exact = metrics_config.get(
                            "final_score_threshold_exact", 0.85
                        )
                        threshold_inexact = metrics_config.get(
                            "final_score_threshold_inexact", 0.9
                        )
                        # Include API metrics in final score if enabled
                        apis_missing = (
                            result.get("apis_missing", [])
                            if metrics_config.get("enable_api_metrics", False)
                            else []
                        )
                        require_api_match = metrics_config.get(
                            "require_api_match", False
                        )
                        final_score = MetricsClass.final_task_score(
                            output_exact_match=result.get("output_exact_match", 0),
                            output_similarity=result.get("output_similarity", 0.0),
                            llm_judge_score=result.get("llm_judge_score"),
                            llm_judge_requested=metrics_config.get(
                                "enable_llm_judge", False
                            ),
                            agent_output=response,
                            threshold_exact=threshold_exact,
                            threshold_inexact=threshold_inexact,
                            apis_missing=apis_missing,
                            require_api_match=require_api_match,
                        )
                        result["task_final_score"] = final_score
                        # Override success based on final score if we have enhanced metrics
                        result["success"] = final_score == 1
                    except Exception as e:
                        logger.warning(f"Failed to compute final score: {e}")
                        result["task_final_score"] = None

        # Log results
        if result["success"]:
            logger.info("✅ PASS: All keywords found")
        else:
            logger.warning(
                f"❌ FAIL: Missing keywords: {keyword_check['missing_keywords']}"
            )
            logger.info(f"   Match rate: {keyword_check['match_rate']:.1%}")

        # Log enhanced metrics if present
        if metrics_config:
            if (
                "output_similarity" in result
                and result["output_similarity"] is not None
            ):
                logger.info(f"   Similarity: {result['output_similarity']:.2f}")
            if "llm_judge_score" in result and result["llm_judge_score"] is not None:
                binary_str = "✓" if result.get("llm_judge_binary") == 1 else "✗"
                logger.info(
                    f"   LLM Judge: {result['llm_judge_score']:.2f} ({binary_str})"
                )
            if "apis_called" in result:
                api_status = "✓" if result.get("apis_correct") == 1 else "✗"
                logger.info(
                    f"   APIs: {len(result.get('apis_called', []))} called, {api_status}"
                )
                if result.get("apis_missing"):
                    logger.info(f"   Missing APIs: {', '.join(result['apis_missing'])}")
            if "task_final_score" in result and result["task_final_score"] is not None:
                final_str = "✓ PASS" if result["task_final_score"] == 1 else "✗ FAIL"
                logger.info(f"   Final Score: {final_str}")

        if tool_calls:
            print(f"\n{'─' * 40} TOOL CALLS {'─' * 40}")
            for tc in tool_calls:
                print(tc)
            print(f"{'─' * 93}\n")

        if tracker_callback:
            tracker_callback(result, keyword_check, intent)

        return result

    except Exception as e:
        import traceback

        logger.error(traceback.format_exc())
        logger.error(f"❌ ERROR in task {task_name}: {e}")

        error_result = {
            "task_name": task_name,
            "difficulty": difficulty,
            "intent": intent,
            "thread_id": thread_id,
            "success": False,
            "match_rate": 0.0,
            "response": "",
            "expected_keywords": expected_keywords,
            "found_keywords": [],
            "missing_keywords": expected_keywords,
            "tool_calls": [],
            "error": str(e),
        }

        if tracker_callback:
            tracker_callback(
                error_result, {"match_rate": 0.0, "all_found": False}, intent
            )

        return error_result


async def evaluate_multiturn_task_with_langfuse(
    agent: CugaAgent,
    turns: List[Dict[str, Any]],
    task_name: str,
    task_index: int,
    langfuse_handler: Optional[Any] = None,
    user_context: Optional[str] = None,
    tracker_callback: Optional[
        Callable[[Dict[str, Any], Dict[str, Any], str], None]
    ] = None,
    track_tool_calls: bool = True,
    expected_keywords: Optional[List[str]] = None,
    task_metadata: Optional[Dict[str, Any]] = None,
    turn_delay: float = 0.2,
) -> Dict[str, Any]:
    """Evaluate a multi-turn task with optional Langfuse tracing.

    Args:
        agent: CugaAgent instance
        turns: List of turn dictionaries, each with 'query' key
        task_name: Name/ID of the task
        task_index: Index of the task (for unique thread_id generation)
        langfuse_handler: Optional Langfuse handler for tracing
        user_context: Optional user context string
        tracker_callback: Optional callback function for tracking
        track_tool_calls: Whether to track tool calls (default: True)
        expected_keywords: Optional list of keywords to check in final response
        task_metadata: Optional metadata dict (domain, difficulty, etc.) to include in results
        turn_delay: Delay in seconds between turns (default: 0.2)

    Returns:
        Evaluation result dictionary
    """
    num_turns = len(turns)
    thread_id = f"multiturn_{task_name}_{task_index}_{uuid.uuid4().hex[:8]}"

    logger.info(f"\n{'=' * 80}")
    logger.info(f"Evaluating multi-turn task: {task_name}")
    logger.info(f"Thread ID: {thread_id} (used for all {num_turns} turns)")
    logger.info(f"Number of turns: {num_turns}")
    logger.info(f"{'=' * 80}")

    initial_intent = turns[0].get("query", "") if turns else ""

    try:
        keyword_check_result = None
        all_responses = []
        all_tool_calls = []
        final_response = None

        if langfuse_handler:
            try:
                from langfuse import get_client

                langfuse = get_client()

                trace_name = f"multiturn_{task_name}_{task_index}"
                predefined_trace_id = langfuse.create_trace_id(
                    seed=f"{task_name}_{task_index}_{thread_id}"
                )

                logger.info(
                    f"📊 Starting Langfuse trace: {trace_name} (ID: {predefined_trace_id})"
                )

                metadata = {"thread_id": thread_id, "task_index": task_index}
                if task_metadata:
                    metadata.update(task_metadata)

                with langfuse.start_as_current_observation(
                    as_type="span",
                    name=trace_name,
                    trace_context={"trace_id": predefined_trace_id},
                    input={
                        "task_name": task_name,
                        "num_turns": num_turns,
                        "turns": [turn.get("query", "") for turn in turns],
                        **(task_metadata or {}),
                    },
                    metadata=metadata,
                ) as span:
                    for turn_idx, turn in enumerate(turns, 1):
                        query = turn.get("query", "")
                        logger.info(f"\n[Turn {turn_idx}/{num_turns}] Query: {query}")
                        logger.info(f"[Turn {turn_idx}] Using thread_id: {thread_id}")

                        invoke_result = await agent.invoke(
                            [HumanMessage(content=query)],
                            thread_id=thread_id,
                            user_context=user_context,
                            track_tool_calls=track_tool_calls,
                        )
                        result_state = invoke_result.answer
                        turn_tool_calls = invoke_result.tool_calls or []
                        all_tool_calls.extend(
                            [(turn_idx, tc) for tc in turn_tool_calls]
                        )

                        all_responses.append(
                            {
                                "turn": turn_idx,
                                "query": query,
                                "response": result_state,
                                "tool_calls": [tc for tc in turn_tool_calls],
                            }
                        )

                        logger.info(f"[Turn {turn_idx}] Response received")

                        if turn_idx < num_turns:
                            await asyncio.sleep(turn_delay)

                    final_response = (
                        all_responses[-1]["response"] if all_responses else None
                    )

                    if expected_keywords and final_response:
                        keyword_check = check_keywords(
                            final_response, expected_keywords
                        )
                        keyword_check_result = keyword_check

                        span.update(
                            output={
                                "final_response": final_response,
                                "all_responses": all_responses,
                                "keyword_results": {
                                    "found_keywords": keyword_check["found_keywords"],
                                    "missing_keywords": keyword_check[
                                        "missing_keywords"
                                    ],
                                    "total_keywords": keyword_check["total_keywords"],
                                    "found_count": keyword_check["found_count"],
                                },
                            },
                            metadata={
                                "thread_id": thread_id,
                                "task_index": task_index,
                                "num_turns": num_turns,
                                **(task_metadata or {}),
                            },
                        )

                        missing_keywords_str = (
                            ", ".join(keyword_check["missing_keywords"])
                            if keyword_check["missing_keywords"]
                            else "none"
                        )
                        span.score_trace(
                            name="keyword_match",
                            value=keyword_check["match_rate"],
                            data_type="NUMERIC",
                            comment=f"Keyword match rate: {keyword_check['found_count']}/{keyword_check['total_keywords']} keywords found. Missing keywords: {missing_keywords_str}",
                        )

                        overall_score = True if keyword_check["all_found"] else False
                        span.score_trace(
                            name="success",
                            value=overall_score,
                            data_type="BOOLEAN",
                            comment="Overall task success: True if all keywords found, otherwise False",
                        )
                    else:
                        span.update(
                            output={
                                "final_response": final_response,
                                "all_responses": all_responses,
                            },
                            metadata={
                                "thread_id": thread_id,
                                "task_index": task_index,
                                "num_turns": num_turns,
                                **(task_metadata or {}),
                            },
                        )

            except Exception as e:
                logger.warning(f"Langfuse tracing failed: {e}")
                for turn_idx, turn in enumerate(turns, 1):
                    query = turn.get("query", "")
                    logger.info(f"\n[Turn {turn_idx}/{num_turns}] Query: {query}")
                    logger.info(f"[Turn {turn_idx}] Using thread_id: {thread_id}")

                    invoke_result = await agent.invoke(
                        [HumanMessage(content=query)],
                        thread_id=thread_id,
                        user_context=user_context,
                        track_tool_calls=track_tool_calls,
                    )
                    result_state = invoke_result.answer
                    turn_tool_calls = invoke_result.tool_calls or []
                    all_tool_calls.extend([(turn_idx, tc) for tc in turn_tool_calls])

                    all_responses.append(
                        {
                            "turn": turn_idx,
                            "query": query,
                            "response": result_state,
                            "tool_calls": [tc for tc in turn_tool_calls],
                        }
                    )

                    if turn_idx < num_turns:
                        await asyncio.sleep(turn_delay)

                final_response = (
                    all_responses[-1]["response"] if all_responses else None
                )

                if expected_keywords and final_response:
                    keyword_check_result = check_keywords(
                        final_response, expected_keywords
                    )
        else:
            for turn_idx, turn in enumerate(turns, 1):
                query = turn.get("query", "")
                logger.info(f"\n[Turn {turn_idx}/{num_turns}] Query: {query}")
                logger.info(f"[Turn {turn_idx}] Using thread_id: {thread_id}")

                invoke_result = await agent.invoke(
                    [HumanMessage(content=query)],
                    thread_id=thread_id,
                    user_context=user_context,
                    track_tool_calls=track_tool_calls,
                )
                result_state = invoke_result.answer
                turn_tool_calls = invoke_result.tool_calls or []
                all_tool_calls.extend([(turn_idx, tc) for tc in turn_tool_calls])

                all_responses.append(
                    {
                        "turn": turn_idx,
                        "query": query,
                        "response": result_state,
                        "tool_calls": [tc for tc in turn_tool_calls],
                    }
                )

                if turn_idx < num_turns:
                    await asyncio.sleep(turn_delay)

            final_response = all_responses[-1]["response"] if all_responses else None

            if expected_keywords and final_response:
                keyword_check_result = check_keywords(final_response, expected_keywords)

        if not keyword_check_result:
            keyword_check_result = {
                "all_found": False,
                "match_rate": 0.0,
                "found_keywords": [],
                "missing_keywords": expected_keywords or [],
                "total_keywords": len(expected_keywords) if expected_keywords else 0,
                "found_count": 0,
            }

        intent = turns[0].get("query", "") if turns else initial_intent

        result = {
            "task_name": task_name,
            "name": task_name,
            "intent": intent,
            "num_turns": num_turns,
            "thread_id": thread_id,
            "response": final_response or "",
            "success": keyword_check_result["all_found"],
            "match_rate": keyword_check_result["match_rate"],
            "expected_keywords": expected_keywords or [],
            "found_keywords": keyword_check_result["found_keywords"],
            "missing_keywords": keyword_check_result["missing_keywords"],
            "final_response": final_response,
            "all_responses": all_responses,
            "tool_calls": [(turn_idx, tc) for turn_idx, tc in all_tool_calls],
            "error": None,
        }

        if task_metadata:
            result.update(task_metadata)

        logger.info(f"✅ Completed: {task_name}")
        if keyword_check_result:
            logger.info(
                f"   Keywords: {keyword_check_result['found_count']}/{keyword_check_result['total_keywords']} found"
            )
            logger.info(f"   Match rate: {keyword_check_result['match_rate']:.2%}")

        if all_tool_calls:
            print(f"\n{'─' * 40} TOOL CALLS ({len(all_tool_calls)} total) {'─' * 30}")
            for turn_idx, tc in all_tool_calls:
                print(f"[Turn {turn_idx}] {tc}")
            print(f"{'─' * 93}\n")

        if tracker_callback:
            tracker_callback(result, keyword_check_result, initial_intent)

        return result

    except Exception as e:
        import traceback

        logger.error(traceback.format_exc())
        logger.error(f"❌ ERROR in multi-turn task {task_name}: {e}")

        intent = turns[0].get("query", "") if turns else ""

        error_result = {
            "task_name": task_name,
            "name": task_name,
            "intent": intent,
            "num_turns": num_turns,
            "thread_id": thread_id,
            "response": "",
            "success": False,
            "match_rate": 0.0,
            "expected_keywords": expected_keywords or [],
            "found_keywords": [],
            "missing_keywords": expected_keywords or [],
            "error": str(e),
            "final_response": None,
            "all_responses": all_responses if "all_responses" in locals() else [],
            "tool_calls": (
                [(turn_idx, tc) for turn_idx, tc in all_tool_calls]
                if "all_tool_calls" in locals()
                else []
            ),
        }

        if task_metadata:
            error_result.update(task_metadata)

        if tracker_callback:
            tracker_callback(
                error_result,
                {
                    "match_rate": 0.0,
                    "all_found": False,
                    "found_keywords": [],
                    "missing_keywords": expected_keywords or [],
                    "total_keywords": len(expected_keywords)
                    if expected_keywords
                    else 0,
                    "found_count": 0,
                },
                intent,
            )

        return error_result


def print_evaluation_summary(results: List[Dict[str, Any]]):
    """Print evaluation summary.

    Args:
        results: List of evaluation result dictionaries
    """
    if not results:
        logger.warning("No results to summarize")
        return

    W = 80  # total width

    def section(title: str) -> str:
        bar = "━" * 4
        rest = W - len(title) - 6
        return f"\n{bar} {title} {'━' * rest}"

    def row(label: str, value: str, label_w: int = 18) -> str:
        return f"  {label:<{label_w}}{value}"

    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed
    avg_match_rate = sum(r["match_rate"] for r in results) / total if total > 0 else 0.0

    has_similarity = any(
        "output_similarity" in r and r["output_similarity"] is not None for r in results
    )
    has_exact_match = any(
        "output_exact_match" in r and r["output_exact_match"] is not None
        for r in results
    )
    has_llm_judge = any(
        "llm_judge_score" in r and r["llm_judge_score"] is not None for r in results
    )
    has_final_score = any(
        "task_final_score" in r and r["task_final_score"] is not None for r in results
    )
    has_api_metrics = any("apis_called" in r for r in results)
    has_api_count = any(
        "api_call_count" in r and "expected_api_count" in r for r in results
    )
    has_tool_recall = any("tool_call_recall" in r for r in results)
    has_latency = any(
        "latency_seconds" in r and r["latency_seconds"] is not None for r in results
    )
    has_tokens = any(
        "tokens_total" in r and r["tokens_total"] is not None for r in results
    )

    by_difficulty: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        diff = result.get("difficulty", "unknown")
        by_difficulty.setdefault(diff, []).append(result)

    # ── Header ────────────────────────────────────────────────────────────────
    print("\n" + "═" * W)
    print("EVALUATION COMPLETE")
    print("═" * W)

    # ── Accuracy section ──────────────────────────────────────────────────────
    print(section("Accuracy"))
    print(row("Pass Rate", f"{passed}/{total}   {passed / total:.1%}"))

    match_rates_list = [
        r["match_rate"] for r in results if r.get("match_rate") is not None
    ]
    kw_full = sum(1 for v in match_rates_list if v == 1.0)
    print(
        row(
            "Keyword Match",
            f"{avg_match_rate:.1%} ± {_std(match_rates_list):.1%}   ({kw_full}/{total} full)",
        )
    )

    if has_final_score:
        fp = sum(1 for r in results if r.get("task_final_score") == 1)
        print(row("Final Score", f"{fp}/{total}   {fp / total:.1%}"))
    if has_exact_match:
        em = sum(1 for r in results if r.get("output_exact_match") == 1)
        print(row("Exact Match", f"{em}/{total}   {em / total:.1%}"))
    if has_similarity:
        sims = [
            r["output_similarity"]
            for r in results
            if r.get("output_similarity") is not None
        ]
        print(row("Similarity", f"{sum(sims) / len(sims):.2f} ± {_std(sims):.2f}"))
    if has_llm_judge:
        js = [
            r["llm_judge_score"]
            for r in results
            if r.get("llm_judge_score") is not None
        ]
        jb = [
            r["llm_judge_binary"]
            for r in results
            if r.get("llm_judge_binary") is not None
        ]
        bp = sum(1 for b in jb if b == 1)
        print(
            row(
                "LLM Judge",
                f"{sum(js) / len(js):.2f} ± {_std(js):.2f}   binary {bp / len(jb):.1%}",
            )
        )

    # Results by difficulty (inline)
    difficulty_order = ["easy", "medium", "hard"]
    sorted_diffs = [d for d in difficulty_order if d in by_difficulty] + [
        d for d in sorted(by_difficulty.keys()) if d not in difficulty_order
    ]
    diff_parts = []
    for d in sorted_diffs:
        dr = by_difficulty[d]
        pc = sum(1 for r in dr if r["success"])
        diff_parts.append(f"{d} {pc}/{len(dr)}")
    print(row("By Difficulty", "   ".join(diff_parts)))

    # ── Tool Calls section ────────────────────────────────────────────────────
    if has_tool_recall:
        tc_results = [r for r in results if "tool_call_recall" in r]
        recall_vals = [r["tool_call_recall"] for r in tc_results]
        precision_vals = [r.get("tool_call_precision", 0) for r in tc_results]
        f1_vals = [r.get("tool_call_f1", 0) for r in tc_results]
        actual_counts = [float(r.get("tool_call_count", 0)) for r in results]
        expected_counts = [
            float(r.get("expected_tool_call_count", 0)) for r in tc_results
        ]

        avg_recall = sum(recall_vals) / len(recall_vals)
        avg_precision = sum(precision_vals) / len(precision_vals)
        avg_f1 = sum(f1_vals) / len(f1_vals)
        avg_actual = sum(actual_counts) / total
        avg_expected = (
            sum(expected_counts) / len(expected_counts) if expected_counts else None
        )
        full_recall = sum(1 for v in recall_vals if v == 1.0)
        total_calls = int(sum(actual_counts))

        print(section("Tool Calls"))
        print(row("F1", f"{avg_f1:.1%} ± {_std(f1_vals):.1%}"))
        print(row("Precision", f"{avg_precision:.1%} ± {_std(precision_vals):.1%}"))
        print(
            row(
                "Recall",
                f"{avg_recall:.1%} ± {_std(recall_vals):.1%}   ({full_recall}/{len(recall_vals)} full coverage)",
            )
        )
        gt_str = (
            f"   ground truth {avg_expected:.1f}" if avg_expected is not None else ""
        )
        print(
            row(
                "Calls / task",
                f"actual {avg_actual:.1f} ± {_std(actual_counts):.1f}{gt_str}   (total {total_calls})",
            )
        )
    elif has_api_metrics:
        api_correct = sum(1 for r in results if r.get("apis_correct") == 1)
        print(section("Tool Calls"))
        print(row("API Accuracy", f"{api_correct}/{total}   {api_correct / total:.1%}"))
        if has_api_count:
            acc = sum(1 for r in results if r.get("api_count_correct") == 1)
            print(row("Count Accuracy", f"{acc}/{total}   {acc / total:.1%}"))

    # ── Performance section ───────────────────────────────────────────────────
    if has_latency or has_tokens:
        print(section("Performance"))
        if has_latency:
            lats = [
                r["latency_seconds"]
                for r in results
                if r.get("latency_seconds") is not None
            ]
            avg_lat = sum(lats) / len(lats)
            print(
                row(
                    "Latency",
                    f"{avg_lat:.1f}s ± {_std(lats):.1f}s   "
                    f"(min {min(lats):.1f}s  max {max(lats):.1f}s  total {sum(lats):.0f}s)",
                )
            )
        if has_tokens:
            tok_results = [r for r in results if r.get("tokens_total") is not None]
            tok_vals = [r["tokens_total"] for r in tok_results]
            total_tok = sum(tok_vals)
            avg_tok = total_tok / len(tok_vals)
            total_in = sum(r.get("tokens_input", 0) or 0 for r in tok_results)
            total_out = sum(r.get("tokens_output", 0) or 0 for r in tok_results)
            print(
                row(
                    "Tokens / task",
                    f"{avg_tok:,.0f} ± {_std(tok_vals):,.0f}   "
                    f"(total {total_tok:,} | in {total_in:,}  out {total_out:,})",
                )
            )

    # ── Failed tasks section ──────────────────────────────────────────────────
    failed_results = [r for r in results if not r["success"]]
    print(section(f"Failed Tasks  ({len(failed_results)}/{total})"))
    if failed_results:
        for result in failed_results:
            print(
                f"\n  ❌ {result['task_name']}  ({result.get('difficulty', 'unknown')})"
            )
            print(f"     Intent : {result['intent']}")
            print(f"     KW     : {result['match_rate']:.1%}", end="")
            if result.get("missing_keywords"):
                print(f"   missing: {', '.join(result['missing_keywords'])}", end="")
            print()
            if result.get("tool_call_f1") is not None:
                calls = result.get("tool_call_count", 0)
                exp = result.get("expected_tool_call_count", "?")
                print(
                    f"     Tools  : {calls}/{exp} calls   "
                    f"P={result.get('tool_call_precision', 0):.0%}  "
                    f"R={result.get('tool_call_recall', 0):.0%}  "
                    f"F1={result['tool_call_f1']:.0%}"
                )
            if result.get("apis_missing"):
                print(f"     Missing APIs : {', '.join(result['apis_missing'])}")
            if result.get("apis_extra"):
                print(f"     Extra APIs   : {', '.join(result['apis_extra'])}")
            if result.get("latency_seconds") is not None:
                print(f"     Latency: {result['latency_seconds']:.1f}s", end="")
                if result.get("tokens_total") is not None:
                    print(f"   Tokens: {result['tokens_total']:,}", end="")
                print()
            if result.get("output_similarity") is not None:
                print(f"     Similarity : {result['output_similarity']:.2f}")
            if result.get("llm_judge_score") is not None:
                b = "✓" if result.get("llm_judge_binary") == 1 else "✗"
                print(f"     LLM Judge  : {result['llm_judge_score']:.2f} ({b})")
            if result.get("error"):
                print(f"     Error : {result['error']}")
    else:
        print("  None! 🎉")

    # ── All results table ─────────────────────────────────────────────────────
    print(section("All Results"))

    has_f1 = any(r.get("tool_call_f1") is not None for r in results)
    has_lat = has_latency
    has_tok = has_tokens

    # Column spec: (header_label, width, align)
    # Single source of truth — used for both the header row and every data row.
    # Status emoji is wide (2 terminal cols) but 1 Python char; we account for
    # this by giving the status column width=3 in the spec but printing the
    # emoji with one trailing space so subsequent columns stay aligned.
    max_name = max((len(r.get("task_name", "")) for r in results), default=10)
    name_w = max(max_name, 4)

    COL_SEP = "  "

    cols: List[tuple] = [
        ("", 2, "<"),  # status (emoji printed separately)
        ("Task", name_w, "<"),
        ("Diff", 6, "<"),
        ("KW", 5, ">"),
    ]
    if has_f1:
        cols += [
            ("F1", 5, ">"),
            ("P", 5, ">"),
            ("R", 5, ">"),
            ("Calls", 7, ">"),
        ]
    if has_lat:
        cols.append(("Latency", 7, ">"))
    if has_tok:
        cols.append(("Tokens", 9, ">"))
    if has_llm_judge:
        cols.append(("LLM", 5, ">"))

    def build_row(cells: List[str]) -> str:
        parts = []
        for (_, w, a), cell in zip(cols, cells):
            parts.append(f"{cell:{a}{w}}")
        return COL_SEP.join(parts)

    header = build_row([h for h, _, _ in cols])
    sep = "─" * len(header)
    print(header)
    print(sep)

    for result in results:
        status = "✅" if result["success"] else "❌"
        task_name = result.get("task_name", "unknown")
        diff = result.get("difficulty", "unknown")
        kw = result.get("match_rate", 0)

        cells = [status, task_name, diff, f"{kw:.0%}"]

        if has_f1:
            f1 = result.get("tool_call_f1")
            pre = result.get("tool_call_precision")
            rec = result.get("tool_call_recall")
            cnt = result.get("tool_call_count", 0)
            exp = result.get("expected_tool_call_count")
            cells += [
                f"{f1:.0%}" if f1 is not None else "—",
                f"{pre:.0%}" if pre is not None else "—",
                f"{rec:.0%}" if rec is not None else "—",
                f"{cnt}/{exp}" if exp is not None else str(cnt),
            ]
        if has_lat:
            lat = result.get("latency_seconds")
            cells.append(f"{lat:.1f}s" if lat is not None else "—")
        if has_tok:
            tok = result.get("tokens_total")
            cells.append(f"{tok:,}" if tok is not None else "—")
        if has_llm_judge:
            llm = result.get("llm_judge_score")
            cells.append(f"{llm:.2f}" if llm is not None else "—")

        print(build_row(cells))
    print()


def flush_langfuse(langfuse_handler: Optional[Any]):
    """Flush Langfuse events in short-lived applications.

    Args:
        langfuse_handler: Optional Langfuse handler
    """
    if langfuse_handler:
        try:
            from langfuse import get_client

            langfuse = get_client()
            langfuse.flush()
            logger.info("✅ Flushed Langfuse events")
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse events: {e}")


def save_evaluation_results(
    results: List[Dict[str, Any]], output_dir: Path, prefix: str = "evaluation"
) -> Path:
    """Save evaluation results to a JSON file.

    Args:
        results: List of evaluation result dictionaries
        output_dir: Output directory path
        prefix: Filename prefix (e.g., "multiturn", "evaluation")

    Returns:
        Path to the saved results file
    """
    from datetime import datetime

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def serialize_tool_calls(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        elif isinstance(obj, tuple) and len(obj) == 2:
            turn_idx, tc = obj
            if hasattr(tc, "model_dump"):
                return {"turn": turn_idx, "tool_call": tc.model_dump()}
            return {"turn": turn_idx, "tool_call": tc}
        return obj

    serializable_results = []
    for result in results:
        serializable_result = {}
        for key, value in result.items():
            if key == "tool_calls" and isinstance(value, list):
                serializable_result[key] = [serialize_tool_calls(tc) for tc in value]
            elif key == "all_responses" and isinstance(value, list):
                serialized_responses = []
                for resp in value:
                    if isinstance(resp, dict) and "tool_calls" in resp:
                        resp_copy = resp.copy()
                        resp_copy["tool_calls"] = [
                            tc if hasattr(tc, "model_dump") else tc
                            for tc in resp["tool_calls"]
                        ]
                        serialized_responses.append(resp_copy)
                    else:
                        serialized_responses.append(resp)
                serializable_result[key] = serialized_responses
            else:
                serializable_result[key] = value
        serializable_results.append(serializable_result)

    total = len(results)
    passed = sum(1 for r in results if r.get("success"))
    avg_match_rate = (
        sum(r.get("match_rate", 0) for r in results) / total if total > 0 else 0
    )

    # Tool call aggregate metrics
    tc_results = [r for r in results if "tool_call_recall" in r]
    total_tool_calls_made = sum(r.get("tool_call_count", 0) for r in results)

    metrics: Dict[str, Any] = {
        "timestamp": timestamp,
        "total_tasks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total > 0 else 0,
        "avg_match_rate": avg_match_rate,
    }
    if tc_results:
        avg_recall = sum(r["tool_call_recall"] for r in tc_results) / len(tc_results)
        avg_precision = sum(r.get("tool_call_precision", 0) for r in tc_results) / len(
            tc_results
        )
        avg_f1 = sum(r.get("tool_call_f1", 0) for r in tc_results) / len(tc_results)
        avg_order = sum(r.get("tool_call_order_score", 0) for r in tc_results) / len(
            tc_results
        )
        avg_actual = total_tool_calls_made / total
        gt_counts = [r.get("expected_tool_call_count", 0) for r in tc_results]
        avg_expected = sum(gt_counts) / len(gt_counts)
        metrics["avg_tool_call_recall"] = round(avg_recall, 3)
        metrics["avg_tool_call_precision"] = round(avg_precision, 3)
        metrics["avg_tool_call_f1"] = round(avg_f1, 3)
        metrics["avg_tool_call_order_score"] = round(avg_order, 3)
        metrics["full_tool_recall_tasks"] = sum(
            1 for r in tc_results if r["tool_call_recall"] == 1.0
        )
        metrics["total_tool_calls_made"] = total_tool_calls_made
        metrics["avg_tool_calls_per_task"] = round(avg_actual, 2)
        metrics["ground_truth_avg_tool_calls"] = round(avg_expected, 2)

    # Latency
    lat_results = [r for r in results if r.get("latency_seconds") is not None]
    if lat_results:
        lats = [r["latency_seconds"] for r in lat_results]
        metrics["avg_latency_seconds"] = round(sum(lats) / len(lats), 2)
        metrics["total_latency_seconds"] = round(sum(lats), 1)

    # Token usage
    tok_results = [r for r in results if r.get("tokens_total") is not None]
    if tok_results:
        metrics["total_tokens"] = sum(r["tokens_total"] for r in tok_results)
        metrics["total_tokens_input"] = sum(
            r.get("tokens_input", 0) or 0 for r in tok_results
        )
        metrics["total_tokens_output"] = sum(
            r.get("tokens_output", 0) or 0 for r in tok_results
        )
        metrics["avg_tokens_per_task"] = round(
            metrics["total_tokens"] / len(tok_results), 1
        )

    output = {
        "metrics": metrics,
        "results": serializable_results,
    }

    output_file = output_dir / f"{prefix}_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    logger.info(f"📁 Results saved to: {output_file}")

    return output_file

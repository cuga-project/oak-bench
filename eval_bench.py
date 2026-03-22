from dataclasses import dataclass

from cuga.backend.activity_tracker.tracker import ActivityTracker
from cuga.backend.cuga_graph.utils.controller import AgentRunner, ExperimentResult
from loguru import logger
import traceback
from pydantic import BaseModel
from typing import List, Dict, Iterable, Any, Optional
import json
import csv
from calculate_test_score import (
    evaluate_test_and_details,
    TestScore,
    TestScoreDetails,
    ToolCall,
)
from statistics import mean
from pathlib import Path
import os
import datetime
from cuga.evaluation.langfuse.get_langfuse_data import LangfuseTraceHandler
import re

tracker = ActivityTracker()


class ExpectedOutput(BaseModel):
    """
    The expected output a test case
    """

    response: str
    keywords: List[str]
    tool_calls: List[ToolCall]


class TestCase(BaseModel):
    """
    This is the model for your test cases, i.e. the input you give the evaluation loop
    """

    app: str
    name: str
    description: str
    intent: str
    task_difficulty: str
    expected_output: ExpectedOutput


@dataclass
class TestMetrics:
    # task_difficulty: Optional[str] = None
    num_steps: Optional[int] = None
    api_calls: Optional[int] = None
    duration: Optional[float] = None
    total_cache_input_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    total_tokens: Optional[int] = None
    total_llm_calls: Optional[int] = None


class TestResult(BaseModel):
    """
    The evaluation loop output of a run on a single test case
    """

    app: str
    index: int
    test_name: str
    task_difficulty: str
    score: TestScore
    details: TestScoreDetails
    metrics: TestMetrics


def dict_subset_with_reason(sup: Dict, sub: Dict, path="") -> List[str]:
    """Return list of reasons why sub is not a subset of sup."""
    reasons = []
    for k, v in sub.items():
        if k not in sup:
            reasons.append(f"Missing key '{path + k}'")
        else:
            sv = sup[k]
            if isinstance(v, dict) and isinstance(sv, dict):
                reasons.extend(dict_subset_with_reason(sv, v, path + k + "."))
            elif sv != v:
                reasons.append(
                    f"Value mismatch at '{path + k}': expected {v}, got {sv}"
                )
    return reasons


def compare_toolcalls(
    a_list: Iterable[ToolCall], b_list: Iterable[ToolCall]
) -> List[str]:
    all_reasons = []
    for a in a_list:
        matched = False
        for b in b_list:
            if b.name in a.name:
                reasons = dict_subset_with_reason(a.args, b.args)
                if not reasons:  # perfect match
                    matched = True
                    break
        if not matched:
            if not any(b.name in a.name for b in b_list):
                all_reasons.append(
                    f"No ToolCall in B has name substring matching '{a.name}'"
                )
            else:
                all_reasons.append(f"Args mismatch for ToolCall '{a.name}'")
                for b in b_list:
                    if b.name in a.name:
                        mismatch = dict_subset_with_reason(a.args, b.args)
                        if mismatch:
                            all_reasons.extend(
                                [f"  vs B({b.name}): {r}" for r in mismatch]
                            )
    return all_reasons


def parse_test_cases(json_file_path: str) -> dict[Any, list[Any]]:
    """Parse JSON test cases into TestCase objects."""

    # Resolve path: use absolute paths as-is, resolve relative paths from user's terminal location
    path = Path(json_file_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    with open(path, "r") as f:
        data = json.load(f)

    test_cases = {}
    for app in data:
        for test_case_data in app["test_cases"]:
            # Extract user input as intent (first user input)
            intent = test_case_data["intent"] if test_case_data["intent"] else ""

            # Parse tool calls
            tool_calls = [
                ToolCall(name=call["name"], args=call["args"])
                for call in test_case_data["expected_output"]["tool_calls"]
            ]

            # Parse expected output
            expected_output = ExpectedOutput(
                response=test_case_data["expected_output"]["response"],
                keywords=test_case_data["expected_output"]["keywords"],
                tool_calls=tool_calls,
            )

            # Create TestCase object
            test_case = TestCase(
                app=app["name"],
                name=test_case_data["name"],
                description=test_case_data["description"],
                intent=intent,
                task_difficulty=test_case_data["difficulty"],
                expected_output=expected_output,
            )

            if app["name"] not in test_cases:
                test_cases[app["name"]] = []
            test_cases[app["name"]].append(test_case)

    return test_cases


async def run_cuga(
    test_file_path: str, json_path: str, tasks_range: tuple
) -> (List[TestCase], List[ExperimentResult]):
    test_cases = parse_test_cases(test_file_path)
    print(
        f"test cases: {len(test_cases['oak-health-insurance'])}\napps: {list(test_cases.keys())}"
    )
    num_tasks = len(test_cases["oak-health-insurance"])
    if tasks_range == (-1, -1):
        first_task = 0
        last_task = num_tasks - 1
    else:
        first_task = tasks_range[0]
        last_task = tasks_range[1]
    if first_task >= num_tasks or last_task >= num_tasks:
        print(f"Error: Task range enter is invalid, max task range is {num_tasks - 1}")
        exit()
    agent_runner = AgentRunner(browser_enabled=False)

    results = []
    for app in test_cases:
        task_ids = [f"{app}_{str(i)}" for i in enumerate(test_cases[app])]
        tracker.start_experiment(task_ids=task_ids, experiment_name=app, description="")
        sum_llm_calls = 0
        sum_tokens = 0
        sum_cost = 0
        sum_cache = 0
        for i, task in enumerate(test_cases[app]):
            if i < first_task:
                continue
            if i > last_task:
                break
            try:
                tracker.reset(intent=task.intent, task_id=f"{app}_{str(i)}")
                # tracker.pi = "{memberId: '121231234', location: (latitude: '40.7128', longitude: '-74.0060'}"
                result = await agent_runner.run_task_generic(
                    eval_mode=False,
                    goal=task.intent,
                    current_datetime=tracker.current_date,
                )
                state = agent_runner.get_current_state()
                state.variables_manager.reset()
                filtered_steps = [
                    step for step in result.steps if "api_call" in step.name
                ]
                result.steps = filtered_steps
                results.append(result)

                langfuse_trace_id = agent_runner.agent_loop_obj.get_langfuse_trace_id()
                langfuse_handler = LangfuseTraceHandler(langfuse_trace_id)
                langfuse_data = await langfuse_handler.get_langfuse_data()

                metrics = TestMetrics()
                if langfuse_data:
                    metrics.total_llm_calls = (
                        langfuse_data.total_llm_calls - sum_llm_calls
                    )
                    metrics.total_tokens = langfuse_data.total_tokens - sum_tokens
                    metrics.total_cost = langfuse_data.total_cost - sum_cost
                    metrics.total_cache_input_tokens = (
                        langfuse_data.total_cache_input_tokens - sum_cache
                    )
                    sum_llm_calls = langfuse_data.total_llm_calls
                    sum_tokens = langfuse_data.total_tokens
                    sum_cost = langfuse_data.total_cost
                    sum_cache = langfuse_data.total_cache_input_tokens
                tracker.finish_task(
                    intent=task.intent,
                    site="",
                    task_id=f"{app}_{str(i)}",
                    eval="",
                    score=result.score,
                    agent_answer=result.answer,
                    exception=False,
                    # difficulty=task.difficulty,
                    agent_v="",
                    total_llm_calls=metrics.total_llm_calls,
                    total_tokens=metrics.total_tokens,
                    total_cost=metrics.total_cost,
                    total_cache_input_tokens=metrics.total_cache_input_tokens,
                )
                task_details = tracker.get_task(f"{app}_{str(i)}")
                # metrics.task_id = task.difficulty
                metrics.duration = task_details["duration"]
                metrics.api_calls = task_details["api_calls"]
                metrics.num_steps = task_details["num_steps"]
                metrics.total_tokens = task_details["total_tokens"]
                parsed_results = parse_test_results(
                    [task], [result], task_id=i, metrics=metrics
                )
                save_test_results(json_path, parsed_results)

            except Exception as e:
                results.append(
                    ExperimentResult(
                        answer=f"Error {e}", score=0, messages=[], steps=[]
                    )
                )
                tracker.finish_task(
                    intent=task.intent,
                    site="",
                    task_id=f"{app}_{str(i)}",
                    eval="",
                    score=0,
                    agent_answer=f"Error: {e}",
                    exception=True,
                    agent_v="",
                )
                logger.error(traceback.format_exc())
                logger.error(e)
    return test_cases, results


def parse_test_results(
    test_cases: List[TestCase],
    experiment_results: List[ExperimentResult],
    task_id: int,
    metrics: TestMetrics,
) -> List[TestResult]:
    if len(test_cases) != len(experiment_results):
        raise ValueError(
            f"Mismatch: {len(test_cases)} test cases vs {len(experiment_results)} results"
        )

    results = []

    for i, (test_case, experiment_result) in enumerate(
        zip(test_cases, experiment_results)
    ):
        # Get answer text (handle None case)
        answer = experiment_result.answer or ""

        keywords = test_case.expected_output.keywords
        expected_tools = [tool for tool in test_case.expected_output.tool_calls]
        tool_calls = []
        for call in experiment_result.steps:
            call_json = json.loads(call.data)
            tool_calls.append(
                ToolCall(name=call_json["function_name"], args=call_json["args"])
            )
        test_score, test_score_details = evaluate_test_and_details(
            keywords,
            tool_calls,
            expected_tools,
            answer,
            test_case.expected_output.response,
        )

        result = TestResult(
            app=test_case.app,
            index=task_id,
            test_name=test_case.name,
            task_difficulty=test_case.task_difficulty,
            score=test_score,
            details=test_score_details,
            metrics=metrics,
        )

        results.append(result)

    return results


def save_test_results(
    json_path: str,
    results: List["TestResult"],
    csv_path: Optional[str] = None,
) -> None:
    """
    Save test results to JSON (as a list) and CSV (append rows, no duplicate headers).
    """

    if csv_path is None:
        csv_path = (
            json_path[:-5] + ".csv"
            if json_path.endswith(".json")
            else json_path + ".csv"
        )

    # ---- JSON ----
    # Load existing results (list), append, then overwrite
    if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
            except json.JSONDecodeError:
                existing = []
    else:
        existing = []

    existing.extend(r.model_dump() for r in results)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    # ---- CSV ----
    def j(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    rows = []
    for r in results:
        rows.append(
            {
                "app": r.app,
                "index": r.index,
                "test_name": r.test_name,
                "task_difficulty": r.task_difficulty,
                "duration": r.metrics.duration,
                "keyword_score": r.score.keyword_score,
                "tool_call_score": r.score.tool_call_score,
                "response_score": r.score.response_score,
                "expected_keywords": j(r.details.expected_keywords),
                "missing_keywords": j(r.details.missing_keywords),
                "tool_call_mismatches": j(
                    [m.model_dump() for m in r.details.tool_call_mismatches]
                ),
                "response_expected": r.details.response_expected,
                "response_actual": r.details.response_actual,
                # "num_steps": r.metrics.num_steps,
                # "api_calls": r.metrics.api_calls,
                "total_tokens": r.metrics.total_tokens,
                "total_llm_calls": r.metrics.total_llm_calls,
                "total_cost": r.metrics.total_cost,
                "total_cache_input_tokens": r.metrics.total_cache_input_tokens,
            }
        )

    write_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(results)} results → JSON: {json_path} | CSV: {csv_path}")


def parse_range(value: str):
    """
    Accept '[start-end]' or 'start-end'. Returns (start, end).
    Examples: '[0-5]', '0-5', '[5-5]'.
    """
    s = value.strip()
    # Try bracketed form first, then plain 'start-end'
    patterns = [r"^\[(\d+)-(\d+)\]$", r"^(\d+)-(\d+)$"]
    for pat in patterns:
        m = re.match(pat, s)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start > end:
                raise argparse.ArgumentTypeError(
                    f"Invalid range: start ({start}) must be <= end ({end})."
                )
            return (start, end)

    raise argparse.ArgumentTypeError(
        f"Invalid format '{value}'. Use [start-end] or start-end, e.g. [0-5] or 0-5."
    )


if __name__ == "__main__":
    import asyncio
    import argparse
    from cuga.config import settings

    tasks_range = (-1, -1)
    settings.update({"ADVANCED_FEATURES": {"TRACKER_ENABLED": True}}, merge=True)
    parser = argparse.ArgumentParser(description="Run tests and save results.")
    parser.add_argument(
        "-t",
        "--test-file-path",
        default="oak_health_test_suite_v1.json",
        help="Path to the test folder",
    )
    # parser.add_argument("-p", "--result-folder-path", default = "logs", help="Path to the result file")
    parser.add_argument(
        "-r",
        "--range",
        type=parse_range,
        required=False,
        help="Range of tasks to run in format [start-end], e.g. [0-5].",
    )

    args = parser.parse_args()

    # test_file_path = "oak_health_test_suite_v1.json"
    timestamp = datetime.datetime.now().strftime("%d_%m_%y_%H_%M")
    result_folder_path = "logs/oak_" + timestamp
    os.makedirs(result_folder_path, exist_ok=True)
    json_path = os.path.join(result_folder_path, "results.json")
    if args.range:
        tasks_range = args.range
    tasks, results = asyncio.run(run_cuga(args.test_file_path, json_path, tasks_range))

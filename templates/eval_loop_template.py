"""
Generalized Evaluation Loop Template for Cuga Benchmarks

This template provides a standardized structure for evaluating agent performance
on benchmark tasks. It can be customized for different benchmarks by:
1. Replacing the config name in load_eval_config()
2. Implementing custom policy loading logic
3. Adjusting the data file format and parsing
4. Customizing user context if needed
5. Optionally integrating with calculate_test_score.py for detailed scoring

Usage:
    python eval_loop_template.py --data path/to/test_data.json
    python eval_loop_template.py --difficulty easy
    python eval_loop_template.py --task specific_task_name
"""

# CRITICAL: Load environment variables FIRST, before ANY other imports
import sys
from pathlib import Path

# Add project root to path to import config_loader from separate directory
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import and call config loader before anything else (from separate directory)
from config_loader import load_eval_config

# TODO: Replace "your_benchmark_name" with your actual benchmark name
# This should match the directory name in benchmarks/ and config file name
load_eval_config("your_benchmark_name")

# Verify env vars are set before importing cuga modules
import os

cuga_logging_dir = os.getenv("CUGA_LOGGING_DIR")
if not cuga_logging_dir:
    raise RuntimeError(
        "CUGA_LOGGING_DIR not set after load_eval_config! Check config files."
    )

# Now safe to import other modules
import asyncio
import json
from typing import List, Dict, Any, Optional
from loguru import logger

logger.info(f"CUGA_LOGGING_DIR: {cuga_logging_dir}")
logger.info(
    f"TRACKER_ENABLED: {os.environ.get('DYNACONF_ADVANCED_FEATURES__TRACKER_ENABLED', 'not set')}"
)

# Import cuga modules (these will read env vars, which are now set)
from cuga.sdk import CugaAgent
from cuga.backend.activity_tracker.tracker import ActivityTracker
from cuga.backend.cuga_graph.state.agent_state import VariablesManager

# Import helpers after cuga modules (helpers import cuga modules too)
from helpers import (
    setup_agent_with_tools,
    clear_all_policies,
    add_policy_via_agent,
    evaluate_task_with_langfuse,
    print_evaluation_summary,
    flush_langfuse,
    create_activity_tracker_callback,
)

# Initialize tracker and variable manager
tracker = ActivityTracker()
var_manager = VariablesManager()

# OPTIONAL: Import calculate_test_score for detailed scoring
# Uncomment the following lines if you want to use calculate_test_score.py
# from calculate_test_score import evaluate_test_and_details, TestScore, TestScoreDetails, ToolCall


class BenchmarkEvaluator:
    """
    Generic evaluator for benchmark tasks.

    This class handles the evaluation loop for running CugaAgent on benchmark tasks.
    Customize the methods as needed for your specific benchmark.
    """

    def __init__(
        self, difficulty_filter: Optional[str] = None, task_id: Optional[str] = None
    ):
        """
        Initialize the evaluator.

        Args:
            difficulty_filter: Filter by difficulty ("easy", "medium", "hard", or None for all)
            task_id: Filter by specific task ID/name (if provided, only this task will be evaluated)
        """
        self.difficulty_filter = difficulty_filter
        self.task_id = task_id
        self.agent: Optional[CugaAgent] = None
        self.langfuse_handler = None
        self.results: List[Dict[str, Any]] = []

    async def setup(self, policies: Optional[List] = None):
        """
        Set up the agent with tools and policies.

        Args:
            policies: Optional list of policies to load. Each policy should be a dict
                     with the structure expected by add_policy_via_agent()
        """
        # Setup agent with tools from registry
        self.agent, self.langfuse_handler = await setup_agent_with_tools()

        # Clear existing policies
        logger.info("Resetting policy database...")
        await clear_all_policies(self.agent)

        # Load policies if provided
        if policies:
            logger.info(f"Loading {len(policies)} policies...")
            for policy in policies:
                await add_policy_via_agent(self.agent, policy)
            logger.info(f"✅ Loaded {len(policies)} policies")
        else:
            logger.info("No policies to load")

    def load_policies(self) -> Optional[List[Dict[str, Any]]]:
        """
        Load benchmark-specific policies.

        Override this method to implement custom policy loading logic.
        For example:
        - Import from a policies module: from your_policies import get_all_policies
        - Load from a JSON file
        - Generate policies programmatically

        Returns:
            List of policy dictionaries, or None if no policies needed
        """
        # TODO: Implement your policy loading logic here
        # Example:
        # from your_policies import get_all_policies
        # return get_all_policies()

        logger.info(
            "No custom policy loading implemented - using default (no policies)"
        )
        return None

    def get_user_context(self, task: Dict[str, Any]) -> Optional[str]:
        """
        Get user context for a specific task.

        Override this method to provide task-specific or benchmark-specific user context.
        User context is additional information passed to the agent about the user's state.

        Args:
            task: The task dictionary

        Returns:
            User context string, or None if no context needed
        """
        # TODO: Implement your user context logic here
        # Example:
        # return """
        # User ID: 12345
        # Location: New York, NY
        # Current Date: 2025-01-15
        # """

        return None

    async def evaluate_task(
        self, task: Dict[str, Any], task_index: int
    ) -> Dict[str, Any]:
        """
        Evaluate a single task.

        Args:
            task: Task dictionary containing at minimum:
                  - "name": task identifier
                  - "intent": the user's goal/query
            task_index: Index of the task (for unique thread_id generation)

        Returns:
            Evaluation result dictionary
        """
        task_name = task.get("name", "unknown")
        intent = task.get("intent", "")

        # Reset tracker and variable manager for fresh state
        tracker.reset(intent=intent, task_id=task_name)
        var_manager.reset()

        # Get user context (can be task-specific)
        user_context = self.get_user_context(task)

        # Create tracker callback
        tracker_callback = create_activity_tracker_callback(tracker, var_manager)

        # Evaluate the task using the helper function
        result = await evaluate_task_with_langfuse(
            agent=self.agent,
            task=task,
            task_index=task_index,
            langfuse_handler=self.langfuse_handler,
            user_context=user_context,
            tracker_callback=tracker_callback,
        )

        # OPTIONAL: Add detailed scoring using calculate_test_score.py
        # Uncomment and customize the following block if you want to use it:
        """
        if "expected_output" in task:
            expected = task["expected_output"]
            keywords = expected.get("keywords", [])
            expected_response = expected.get("response", "")
            expected_tool_calls = [
                ToolCall(name=tc["name"], args=tc["args"])
                for tc in expected.get("tool_calls", [])
            ]
            
            # Extract actual tool calls from result
            actual_tool_calls = []
            # TODO: Parse actual tool calls from result based on your result format
            
            # Calculate detailed scores
            test_score, test_score_details = evaluate_test_and_details(
                expected_keywords=keywords,
                tool_calls=actual_tool_calls,
                expected_tool_calls=expected_tool_calls,
                response=result.get("answer", ""),
                expected_response=expected_response,
            )
            
            # Add scores to result
            result["test_score"] = test_score.model_dump()
            result["test_score_details"] = test_score_details.model_dump()
        """

        return result

    def parse_test_data(self, data_path: str) -> List[Dict[str, Any]]:
        """
        Parse test data from file.

        Override this method to implement custom data parsing logic for your benchmark.

        Args:
            data_path: Path to the test data file

        Returns:
            List of test case dictionaries. Each should contain at minimum:
            - "name": task identifier
            - "intent": the user's goal/query
            - "difficulty": (optional) difficulty level for filtering
        """
        # Load JSON data
        with open(data_path, "r") as f:
            data = json.load(f)

        # TODO: Customize this parsing logic for your data format
        # Default format: list of apps, each with test_cases
        test_cases = []

        # Handle both formats: direct list of test cases or nested in apps
        if isinstance(data, list):
            if data and "test_cases" in data[0]:
                # Format: [{"name": "app1", "test_cases": [...]}, ...]
                for app_data in data:
                    if "test_cases" in app_data:
                        test_cases.extend(app_data["test_cases"])
            else:
                # Format: direct list of test cases
                test_cases = data
        elif isinstance(data, dict) and "test_cases" in data:
            # Format: {"test_cases": [...]}
            test_cases = data["test_cases"]
        else:
            raise ValueError(f"Unsupported data format in {data_path}")

        return test_cases

    async def evaluate_all(self, data_path: str):
        """
        Evaluate all tasks from the data file.

        Args:
            data_path: Path to test data file
        """
        # Parse test data
        test_cases = self.parse_test_data(data_path)

        # Filter by task_id if specified (takes precedence over difficulty filter)
        if self.task_id:
            test_cases = [
                tc
                for tc in test_cases
                if tc.get("name", "").lower() == self.task_id.lower()
            ]
            if not test_cases:
                logger.error(f"Task '{self.task_id}' not found in test data")
                return
            logger.info(f"Filtered to task: {self.task_id}")
        # Filter by difficulty if specified
        elif self.difficulty_filter:
            test_cases = [
                tc
                for tc in test_cases
                if tc.get("difficulty", "").lower() == self.difficulty_filter.lower()
            ]
            logger.info(f"Filtered to {len(test_cases)} {self.difficulty_filter} tasks")
        else:
            logger.info(f"Evaluating all {len(test_cases)} tasks")

        # Start experiment tracking
        # TODO: Customize experiment name via environment variable or config
        experiment_name = os.getenv("EXPERIMENT_NAME", "benchmark_evaluation")
        task_ids = [tc.get("name", f"task_{i}") for i, tc in enumerate(test_cases, 1)]
        tracker.start_experiment(
            task_ids=task_ids,
            experiment_name=experiment_name,
            description="Benchmark evaluation",
        )

        # Evaluate each task
        self.results = []
        for i, task in enumerate(test_cases, 1):
            logger.info(
                f"\n[{i}/{len(test_cases)}] Processing task: {task.get('name', 'unknown')}..."
            )

            try:
                # Pass task index to generate unique thread_id and ensure fresh state
                result = await self.evaluate_task(task, task_index=i)
                self.results.append(result)
            except Exception as e:
                logger.error(
                    f"Error evaluating task {task.get('name', 'unknown')}: {e}"
                )
                import traceback

                traceback.print_exc()
                # Add failed result
                self.results.append(
                    {
                        "task_name": task.get("name", "unknown"),
                        "success": False,
                        "error": str(e),
                        "score": 0.0,
                    }
                )

            # Small delay to avoid rate limiting between tasks
            if i < len(test_cases):  # Don't sleep after last task
                await asyncio.sleep(0.5)

        # Flush langfuse data
        flush_langfuse(self.langfuse_handler)

    def print_summary(self):
        """Print evaluation summary."""
        print_evaluation_summary(self.results)


async def main():
    """Main evaluation function."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate benchmark tasks")
    parser.add_argument(
        "--difficulty",
        type=str,
        choices=["easy", "medium", "hard"],
        default=None,
        help="Filter by difficulty level (default: all)",
    )

    # TODO: Update default data file path for your benchmark
    default_data_file = os.getenv("DATA_FILE", "test_data.json")
    parser.add_argument(
        "--data",
        type=str,
        default=os.path.join(os.path.dirname(__file__), default_data_file),
        help=f"Path to data file (default: {default_data_file})",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Run a specific task by ID/name. Overrides --difficulty filter.",
    )

    args = parser.parse_args()

    # Create evaluator
    evaluator = BenchmarkEvaluator(difficulty_filter=args.difficulty, task_id=args.task)

    try:
        # Load policies (customize in load_policies method)
        policies = evaluator.load_policies()

        # Setup agent with tools and policies
        await evaluator.setup(policies=policies)

        # Evaluate all tasks
        await evaluator.evaluate_all(args.data)

        # Print summary
        evaluator.print_summary()

    except KeyboardInterrupt:
        logger.warning("\nEvaluation interrupted by user")
        if evaluator.results:
            evaluator.print_summary()
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

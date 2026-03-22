"""Evaluation loop for Oak Health Insurance tasks.

This script:
1. Loads tools from the registry
2. Evaluates each task in oak_data.json
3. Checks keywords in responses
4. Reports results with filtering by difficulty
"""

# CRITICAL: Load environment variables FIRST, before ANY other imports
import sys
from pathlib import Path

# Add project root to path to import config_loader from separate directory
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import and call config loader before anything else (from separate directory)
from config_loader import load_eval_config

load_eval_config("oak_health_insurance")

# Now safe to import other modules
import os
import asyncio
import json
from typing import List, Dict, Any, Optional
from loguru import logger

# Import cuga modules (these will read env vars, which are now set)
from cuga.sdk import CugaAgent
from cuga.backend.activity_tracker.tracker import ActivityTracker
from cuga.backend.cuga_graph.state.agent_state import VariablesManager

# Import helpers after cuga modules (helpers import cuga modules too)
from helpers import (
    setup_agent_with_tools,
    clear_all_policies,
    evaluate_task_with_langfuse,
    print_evaluation_summary,
    flush_langfuse,
    create_activity_tracker_callback,
    save_evaluation_results,
    MetricsConfig,
    TokenUsageCallback,
)

tracker = ActivityTracker()
var_manager = VariablesManager()


class OakEvaluator:
    """Evaluator for Oak Health Insurance tasks."""

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
        self.results: List[Dict[str, Any]] = []
        self.user_info: List[str] = []
        self.token_callback = TokenUsageCallback()

    async def setup(self):
        """Set up the agent with tools."""
        self.agent, self.langfuse_handler = await setup_agent_with_tools(
            extra_callbacks=[self.token_callback]
        )

        self.agent._auto_load_policies = False

        logger.info("Resetting policy database...")
        await clear_all_policies(self.agent)
        logger.info("✅ Agent ready")

    async def setup_without_policies(self):
        """Set up the agent with tools but no policies (clears any existing ones)."""
        self.agent, self.langfuse_handler = await setup_agent_with_tools(
            extra_callbacks=[self.token_callback]
        )

        # Disable auto-loading BEFORE clearing, so the clear isn't immediately
        # undone by the next policy check re-loading from the .cuga folder on disk.
        self.agent._auto_load_policies = False

        logger.info("Resetting policy database (no policies will be loaded)...")
        await clear_all_policies(self.agent)
        logger.info("✅ Policy database cleared — running without policies")

    async def evaluate_task(
        self, task: Dict[str, Any], task_index: int
    ) -> Dict[str, Any]:
        """Evaluate a single task.

        Args:
            task: Task dictionary from oak_data.json
            task_index: Index of the task (for unique thread_id generation)

        Returns:
            Evaluation result dictionary
        """
        task_name = task.get("name", "unknown")
        intent = task.get("intent", "")

        tracker.reset(intent=intent, task_id=task_name)
        var_manager.reset()

        user_context = "\n".join(self.user_info) if self.user_info else ""

        tracker_callback = create_activity_tracker_callback(tracker, var_manager)

        return await evaluate_task_with_langfuse(
            agent=self.agent,
            task=task,
            task_index=task_index,
            langfuse_handler=self.langfuse_handler,
            user_context=user_context,
            tracker_callback=tracker_callback,
            track_tool_calls=True,
            metrics_config=MetricsConfig(enable_api_metrics=True),
            token_callback=self.token_callback,
        )

    async def evaluate_all(self, oak_data_path: str = "oak_data.json"):
        """
        Evaluate all tasks from oak_data.json.

        Args:
            oak_data_path: Path to oak_data.json file
        """
        # Load test data
        with open(oak_data_path, "r") as f:
            data = json.load(f)

        # Extract test cases and collect user_info across all app suites
        test_cases = []
        self.user_info = []
        for app_data in data:
            if "user_info" in app_data:
                self.user_info.extend(app_data["user_info"])
            if "test_cases" in app_data:
                test_cases.extend(app_data["test_cases"])

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
        experiment_name = os.getenv("OAK_EXPERIMENT_NAME", "oak_health_evaluation")
        task_ids = [tc.get("name", f"task_{i}") for i, tc in enumerate(test_cases, 1)]
        tracker.start_experiment(
            task_ids=task_ids,
            experiment_name=experiment_name,
            description="Oak Health Insurance benchmark evaluation",
        )

        # Evaluate each task
        self.results = []
        for i, task in enumerate(test_cases, 1):
            logger.info(f"\n[{i}/{len(test_cases)}] Processing task...")
            # Pass task index to generate unique thread_id and ensure fresh state
            result = await self.evaluate_task(task, task_index=i)
            self.results.append(result)

            # Small delay to avoid rate limiting between tasks
            if i < len(test_cases):  # Don't sleep after last task
                await asyncio.sleep(0.5)

        flush_langfuse(self.langfuse_handler)

    def print_summary(self):
        """Print evaluation summary."""
        print_evaluation_summary(self.results)

    def save_results(self, output_dir: Optional[str] = None):
        """Save evaluation results to JSON files."""
        if output_dir is None:
            output_dir = Path(__file__).parent / "results"
        return save_evaluation_results(self.results, output_dir, prefix="oak_health")


async def main():
    """Main evaluation function."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate Oak Health Insurance tasks")
    parser.add_argument(
        "--difficulty",
        type=str,
        choices=["easy", "medium", "hard"],
        default=None,
        help="Filter by difficulty level (default: all)",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=os.path.join(
            os.path.dirname(__file__), "oak_health_test_suite_v1.json"
        ),
        help="Path to oak_data.json (default: oak_data.json)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Run a specific task by ID/name (e.g., 'care_providers_mri'). Overrides --difficulty filter.",
    )
    parser.add_argument(
        "--no-policy",
        action="store_true",
        help="Run without policies (default: policies enabled)",
    )

    args = parser.parse_args()

    # Create evaluator
    evaluator = OakEvaluator(difficulty_filter=args.difficulty, task_id=args.task)

    try:
        # Setup
        if args.no_policy:
            await evaluator.setup_without_policies()
        else:
            await evaluator.setup()

        # Evaluate
        await evaluator.evaluate_all(args.data)

        # Print summary
        evaluator.print_summary()

        # Save results
        evaluator.save_results()

    except KeyboardInterrupt:
        logger.warning("\nEvaluation interrupted by user")
        if evaluator.results:
            evaluator.print_summary()
            evaluator.save_results()
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

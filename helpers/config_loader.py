"""Configuration loader for evaluation benchmarks.

This module provides functions to load environment variables from config files
without importing heavy dependencies like cuga agent.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def load_eval_config(benchmark_name: str):
    """Load environment variables from config files.

    This function loads configuration in the following order:
    1. config/global.env (shared settings, not overridden)
    2. config/{benchmark_name}.env (benchmark-specific settings, not overridden)

    Args:
        benchmark_name: Name of the benchmark (e.g., "m3", "oak_health_insurance")
    """
    # Get project root (assuming this file is in helpers/)
    current_file = Path(__file__)
    project_root = current_file.parent.parent
    config_dir = project_root / "config"

    # Load global.env (shared settings)
    # Use override=True to ensure our config values take precedence
    global_env = config_dir / "global.env"
    if global_env.exists():
        load_dotenv(global_env, override=True)

    # Load benchmark-specific .env from config directory
    # Use override=True to ensure benchmark-specific values take precedence
    benchmark_env = project_root / "config" / f"{benchmark_name}.env"
    if benchmark_env.exists():
        load_dotenv(benchmark_env, override=True)

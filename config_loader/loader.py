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
    # Get project root (assuming this file is in config_loader/)
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

    # Convert CUGA_LOGGING_DIR to absolute path if it's relative
    # This must be done BEFORE any cuga modules are imported
    # CRITICAL: cuga.config reads this at module import time (line 21), so it must be set now
    # cuga.config does: LOGGING_DIR = os.environ.get("CUGA_LOGGING_DIR", ...)
    # So we MUST set os.environ["CUGA_LOGGING_DIR"] before cuga.config is imported
    cuga_logging_dir = os.getenv("CUGA_LOGGING_DIR")
    if cuga_logging_dir:
        # Remove quotes if present (from env file)
        cuga_logging_dir = str(cuga_logging_dir).strip('"').strip("'")
        logging_path = Path(cuga_logging_dir)

        if not logging_path.is_absolute():
            # Join with project root to make it absolute
            absolute_logging_dir = (project_root / logging_path).resolve()
        else:
            # Already absolute, but resolve it to ensure it's normalized
            absolute_logging_dir = logging_path.resolve()

        # CRITICAL: Set it in os.environ so cuga.config can read it
        os.environ["CUGA_LOGGING_DIR"] = str(absolute_logging_dir)
    else:
        # Force set it even if not in env file (use default location)
        default_logging_dir = (project_root / "logging").resolve()
        os.environ["CUGA_LOGGING_DIR"] = str(default_logging_dir)

    # Verify the env var is set (for debugging)
    final_logging_dir = os.getenv("CUGA_LOGGING_DIR")
    if final_logging_dir:
        # Use print instead of logger to avoid importing loguru
        print(
            f"[config_loader] CUGA_LOGGING_DIR set to: {final_logging_dir}",
            file=sys.stderr,
        )
    else:
        print("[config_loader] WARNING: CUGA_LOGGING_DIR not set!", file=sys.stderr)

    # Convert APPWORLD_ROOT to absolute path if it's relative
    appworld_root = os.getenv("APPWORLD_ROOT")
    if appworld_root:
        appworld_root = str(appworld_root).strip('"').strip("'")
        appworld_path = Path(appworld_root)

        if not appworld_path.is_absolute():
            absolute_appworld_root = (project_root / appworld_path).resolve()
        else:
            absolute_appworld_root = appworld_path.resolve()

        os.environ["APPWORLD_ROOT"] = str(absolute_appworld_root)
        print(
            f"[config_loader] APPWORLD_ROOT set to: {absolute_appworld_root}",
            file=sys.stderr,
        )

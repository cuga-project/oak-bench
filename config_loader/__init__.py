"""Configuration loader for evaluation benchmarks.

This module is in a separate directory to avoid importing cuga modules
when loading environment variables.
"""

from .loader import load_eval_config

__all__ = ["load_eval_config"]

#!/usr/bin/env python3
"""
Unified benchmark runner — starts all required services, runs evaluation,
and optionally repeats runs to report aggregate statistics.

Usage:
    uv run run.py <benchmark> [options]

Benchmarks:
    oak_health        Oak Health Insurance only  (port 8090)

Options:
    --rep N            Repeat evaluation N times; report mean ± std  (default: 1)
    --difficulty LEVEL Filter tasks by difficulty: easy | medium | hard
    --task ID          Run a single task by name (overrides --difficulty)
    --no-cleanup       Leave services running after evaluation (useful for debugging)

Examples:
    uv run run.py oak_health
    uv run run.py oak_health --rep 5
    uv run run.py oak_health --difficulty easy --rep 3
    uv run run.py oak_health --task approved_claims
"""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# ──────────────────────────────────────────────────────────────────────────────
# Project layout
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent

BENCHMARK_CONFIGS: Dict[str, dict] = {
    "oak_health": {
        "description": "Oak Health Insurance",
        "apps": [
            {
                "dir": PROJECT_ROOT / "oak_health",
                "port": 8090,
                "name": "Oak Health",
                "module": "oak_health.main:app",
            },
        ],
        "mcp_servers_file": "oak_health/oak_mcp_servers.yaml",
        "eval_args": [],  # default test suite in eval_bench_sdk.py
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Environment helpers
# ──────────────────────────────────────────────────────────────────────────────


def _load_dotenv_into(path: Path, env: dict) -> None:
    """Load key=value pairs from a dotenv file into *env*, overriding existing values."""
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            env[key] = val  # override — same behaviour as config_loader (override=True)


def build_env(mcp_servers_file: str) -> dict:
    """Return an env dict with config loaded and MCP_SERVERS_FILE set."""
    env = os.environ.copy()
    _load_dotenv_into(PROJECT_ROOT / ".env", env)
    _load_dotenv_into(PROJECT_ROOT / "config" / "global.env", env)
    _load_dotenv_into(PROJECT_ROOT / "config" / "oak_health_insurance.env", env)
    # Always use an absolute path so the registry can find the file regardless of cwd
    env["MCP_SERVERS_FILE"] = str(PROJECT_ROOT / mcp_servers_file)
    return env


# ──────────────────────────────────────────────────────────────────────────────
# Service management
# ──────────────────────────────────────────────────────────────────────────────


def free_port(port: int) -> None:
    """Kill any process currently listening on *port* (best-effort)."""
    import signal as _signal

    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), _signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
        if pids:
            time.sleep(1)  # give processes a moment to die
    except FileNotFoundError:
        pass  # lsof not available


def start_app(
    app_dir: Path, port: int, env: dict, module: str = "main:app"
) -> subprocess.Popen:
    """Start a FastAPI app (no auto-reload for cleaner process management)."""
    return subprocess.Popen(
        ["uv", "run", "uvicorn", module, "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,  # capture stderr to surface on failure
    )


def start_registry(env: dict) -> subprocess.Popen:
    """Start the CUGA registry (reads MCP_SERVERS_FILE from env)."""
    # Route output to terminal so startup errors are visible
    return subprocess.Popen(
        ["uv", "run", "registry"],
        cwd=PROJECT_ROOT,
        env=env,
    )


def wait_for_app(port: int, name: str, timeout: int = 90) -> bool:
    """Poll until the app's OpenAPI endpoint responds."""
    url = f"http://127.0.0.1:{port}/openapi.json"
    deadline = time.time() + timeout
    print(f"  Waiting for {name} on port {port} ", end="", flush=True)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                print(" ✓")
                return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(2)
    print(" ✗ (timed out)")
    return False


def wait_for_registry(expected_app_names: List[str], timeout: int = 120) -> bool:
    """
    Poll http://localhost:8001/applications until all expected apps appear.

    The registry uses 'fastapi dev' which takes variable time to start, and
    then calls start_servers() (fetches each app's OpenAPI spec) before it
    becomes useful. Polling the /applications endpoint is the only reliable
    way to confirm everything is wired up.
    """
    url = "http://localhost:8001/applications"
    deadline = time.time() + timeout
    print(
        f"  Waiting for registry to register {expected_app_names} ", end="", flush=True
    )
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
                registered = [
                    entry.get("name", entry) if isinstance(entry, dict) else entry
                    for entry in data
                ]
                if all(app in registered for app in expected_app_names):
                    print(f" ✓  (registered: {registered})")
                    return True
                # Registry responded but apps not yet registered — keep polling
                print(".", end="", flush=True)
        except Exception:
            print(".", end="", flush=True)
        time.sleep(3)
    print(" ✗ (timed out)")
    return False


def kill_all(processes: List[subprocess.Popen]) -> None:
    """Gracefully terminate, then force-kill if needed."""
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for p in processes:
        try:
            if p.poll() is None:
                p.kill()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Evaluation
# ──────────────────────────────────────────────────────────────────────────────


def run_eval(extra_args: List[str], env: dict) -> Optional[Path]:
    """
    Run eval_bench_sdk.py, let its output stream to the terminal,
    and return the path to the results JSON written by save_results().
    """
    results_dir = PROJECT_ROOT / "results"
    before = set(results_dir.glob("*.json")) if results_dir.exists() else set()

    cmd = [sys.executable, str(PROJECT_ROOT / "eval_bench_sdk.py")] + extra_args
    subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)

    after = set(results_dir.glob("*.json")) if results_dir.exists() else set()
    new_files = after - before
    if not new_files:
        return None
    return max(new_files, key=lambda p: p.stat().st_mtime)


def read_metrics(results_file: Path) -> dict:
    """Return the metrics dict from a saved results JSON."""
    with open(results_file) as f:
        data = json.load(f)
    return data.get("metrics", {})


# ──────────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ──────────────────────────────────────────────────────────────────────────────


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def print_aggregate(label: str, values: List[float]) -> None:
    if not values:
        return
    runs_str = "  ".join(_fmt_pct(v) for v in values)
    print(
        f"  {label:16s}  mean={_fmt_pct(_mean(values))}  std={_fmt_pct(_std(values))}   [{runs_str}]"
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Oak benchmark evaluations with automatic service management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "benchmark",
        choices=list(BENCHMARK_CONFIGS.keys()),
        metavar="benchmark",
        help="oak_health",
    )
    parser.add_argument(
        "--rep",
        type=int,
        default=1,
        metavar="N",
        help="Repeat evaluation N times and report mean ± std (default: 1)",
    )
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        default=None,
        help="Filter tasks by difficulty",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Run a single task by name/ID",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Leave services running after evaluation",
    )
    args = parser.parse_args()

    if args.rep < 1:
        parser.error("--rep must be >= 1")

    config = BENCHMARK_CONFIGS[args.benchmark]
    processes: List[subprocess.Popen] = []

    # ── Cleanup handler ───────────────────────────────────────────────────────
    def cleanup(sig=None, _frame=None) -> None:
        if not args.no_cleanup and processes:
            print("\nShutting down services...")
            kill_all(processes)
            processes.clear()
        sys.exit(1 if sig else 0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║           Oak Benchmark Runner                   ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Benchmark  : {args.benchmark}  ({config['description']})")
    print(f"  Runs       : {args.rep}")
    if args.difficulty:
        print(f"  Difficulty : {args.difficulty}")
    if args.task:
        print(f"  Task       : {args.task}")
    print()

    # ── Start services ────────────────────────────────────────────────────────
    env = build_env(config["mcp_servers_file"])

    # Step 1: start FastAPI apps
    print("Starting FastAPI apps...")
    free_port(8001)  # registry port
    for app in config["apps"]:
        free_port(app["port"])
        print(f"  Starting {app['name']} (port {app['port']})...")
        processes.append(
            start_app(app["dir"], app["port"], env, app.get("module", "main:app"))
        )

    # Step 2: wait until every app is reachable — BEFORE starting the registry,
    # because the registry fetches the OpenAPI spec immediately on startup.
    print()
    print("Waiting for apps to be ready...")
    for app in config["apps"]:
        if not wait_for_app(app["port"], app["name"]):
            print(f"\n[ERROR] {app['name']} did not start within the timeout.")
            cleanup()
            return

    # Step 3: start the registry now that all apps are up
    print()
    print("Starting registry...")
    processes.append(start_registry(env))

    # Poll until the registry has actually registered all expected apps.
    # The registry runs via 'fastapi dev' (variable startup time) and calls
    # start_servers() which fetches each app's OpenAPI spec — we must wait
    # for that to complete before starting the eval, otherwise the agent
    # gets 0 tools and fails silently.
    # These are the service names as they appear in the YAML files and registry
    expected_app_names = {
        "oak_health": ["oak_health_insurance"],
    }[args.benchmark]

    if not wait_for_registry(expected_app_names):
        print("\n[ERROR] Registry did not register the expected apps in time.")
        print(
            "        Check that MCP_SERVERS_FILE is correct and the FastAPI apps are reachable."
        )
        cleanup()
        return
    print()

    # ── Build eval args ───────────────────────────────────────────────────────
    eval_args = list(config["eval_args"])
    if args.difficulty:
        eval_args += ["--difficulty", args.difficulty]
    if args.task:
        eval_args += ["--task", args.task]

    # ── Run evaluation(s) ─────────────────────────────────────────────────────
    pass_rates: List[float] = []
    match_rates: List[float] = []
    recall_rates: List[float] = []
    precision_rates: List[float] = []
    f1_rates: List[float] = []
    order_rates: List[float] = []
    latencies: List[float] = []

    for run_idx in range(1, args.rep + 1):
        if args.rep > 1:
            sep = "─" * 52
            print(sep)
            print(f"  Run {run_idx} / {args.rep}")
            print(sep)

        results_file = run_eval(eval_args, env)

        if results_file:
            m = read_metrics(results_file)
            pr = m.get("pass_rate", 0.0)
            mr = m.get("avg_match_rate", 0.0)
            rec = m.get("avg_tool_call_recall")
            pre = m.get("avg_tool_call_precision")
            f1 = m.get("avg_tool_call_f1")
            ord_ = m.get("avg_tool_call_order_score")
            lat = m.get("avg_latency_seconds")

            pass_rates.append(pr)
            match_rates.append(mr)
            if rec is not None:
                recall_rates.append(rec)
            if pre is not None:
                precision_rates.append(pre)
            if f1 is not None:
                f1_rates.append(f1)
            if ord_ is not None:
                order_rates.append(ord_)
            if lat is not None:
                latencies.append(lat)

            if args.rep > 1:
                parts = [f"pass={_fmt_pct(pr)}", f"kw={_fmt_pct(mr)}"]
                if f1 is not None:
                    parts.append(f"f1={_fmt_pct(f1)}")
                if lat is not None:
                    parts.append(f"lat={lat:.1f}s")
                print(f"\n  → Run {run_idx}: " + "  ".join(parts))
        else:
            print(f"\n  [!] No results file found for run {run_idx}")

    # ── Aggregate stats (only shown when --rep > 1) ───────────────────────────
    if args.rep > 1 and pass_rates:
        print()
        print("╔══════════════════════════════════════════════════╗")
        print(f"║  AGGREGATE RESULTS  ({args.rep} runs)             ")
        print("╚══════════════════════════════════════════════════╝")
        print_aggregate("Pass Rate", pass_rates)
        print_aggregate("Match Rate", match_rates)
        if recall_rates:
            print_aggregate("TC Recall", recall_rates)
        if precision_rates:
            print_aggregate("TC Precision", precision_rates)
        if f1_rates:
            print_aggregate("TC F1", f1_rates)
        if order_rates:
            print_aggregate("TC Order", order_rates)
        if latencies:
            lat_mean = _mean(latencies)
            lat_std = _std(latencies)
            print(f"  {'Avg Latency':16s}  mean={lat_mean:.1f}s  std={lat_std:.1f}s")
        print()

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if not args.no_cleanup:
        print("Shutting down services...")
        kill_all(processes)
        processes.clear()
        print("Done.")
    else:
        print("Services left running (--no-cleanup). PIDs:", [p.pid for p in processes])


if __name__ == "__main__":
    main()

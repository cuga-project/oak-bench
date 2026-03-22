# Oak Bench

Oak Bench exists so you can **evaluate agent reliability and safety** on realistic workloads: do agents follow the right procedures, respect constraints, and **adhere to policies** instead of drifting or cutting corners? **Oak Health Insurance** is the first scenario—a lifelike healthcare insurance setting you can run and score with the benchmark harness.

---

## What's in this repo

| Purpose | What to use |
|---|---|
| **Demo / showcase** | Install `oak_health/` as a package and run `cuga-oak-health` |
| **Agent evaluation** | Run `uv run run.py oak_health` from the repo root |
| **Unit tests** | Run `pytest` from `oak_health/tests/` |

---

## Repository Structure

```
oak-benchmark/
├── run.py                          # Benchmark runner (starts services + runs eval)
├── eval_bench_sdk.py               # Evaluation script
├── oak_health_test_suite_v1.json   # Benchmark task definitions
├── config/
│   ├── global.env                  # Shared configuration
│   └── oak_health_insurance.env    # App-specific configuration
├── helpers/                        # Eval helper modules and scripts
├── oak_health/                       # The Health API — installable package
│   ├── pyproject.toml              # Package metadata and entry points
│   ├── src/
│   │   └── oak_health/             # Core FastAPI application
│   │       ├── main.py             # FastAPI app (port 8090)
│   │       ├── models.py           # Pydantic models
│   │       └── data.py             # Seed data and fixtures
│   ├── oak_mcp_servers.yaml        # MCP server config (used by CUGA registry)
│   └── tests/                      # Unit tests for the API
└── scripts/                        # Visualization utilities
```

---

## Oak Health Insurance — demo app

The `oak_health/` directory is the Oak Health Insurance package: a self-contained Python package. Install it once, then launch the server with a single command.

### Install

```bash
cd oak_health
uv pip install .
```

### Run

```bash
uv run cuga-oak-health
```

This starts the FastAPI server at **http://localhost:8090**.

Interactive API docs are available at **http://localhost:8090/docs**.

---

## Oak Health Insurance — benchmark

The benchmark runner (`run.py`) automatically starts the Oak Health Insurance FastAPI app and CUGA registry, runs the evaluation, then shuts everything down.

### Prerequisites

- CUGA Agent installed at `../cuga-agent`
- API keys configured in `.env` (see below)

### Setup

```bash
# 1. Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv sync

# 2. Configure API keys
cp .env.example .env   # or: touch .env
```

Add to `.env`:
```env
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key

# Optional — Langfuse tracing
LANGFUSE_SECRET_KEY=your-secret-key
LANGFUSE_PUBLIC_KEY=your-public-key
LANGFUSE_HOST=http://localhost:3000
```

### Run the benchmark

```bash
uv run run.py oak_health
```

### Options

```bash
# Repeat N times and report mean ± std
uv run run.py oak_health --rep 5

# Filter by difficulty
uv run run.py oak_health --difficulty easy
uv run run.py oak_health --difficulty medium
uv run run.py oak_health --difficulty hard

# Run a single task
uv run run.py oak_health --task approved_claims

# Keep services running after eval (useful for debugging)
uv run run.py oak_health --no-cleanup
```

### Results

```bash
# Open visualization dashboard
./scripts/viz.sh oak_health_insurance
```

Results are written to `results/` (JSON) and `logging/`.

---

## Unit Tests

Tests live in `oak_health/tests/` and cover every API endpoint.

```bash
cd oak_health/tests
pytest
```

Or from the repo root:

```bash
pytest oak_health/tests/
```

---

## Configuration

### `config/oak_health_insurance.env`

Key settings:

```env
MCP_SERVERS_FILE="oak_health/oak_mcp_servers.yaml"
CUGA_LOGGING_DIR="./logging"
```

Advanced CUGA agent settings:

```env
DYNACONF_ADVANCED_FEATURES__CUGA_MODE = "accurate"
DYNACONF_FEATURES__FORCED_APPS = ["oak_health_insurance"]
DYNACONF_FEATURES__LOCAL_SANDBOX = true
```

### `config/global.env`

Shared settings applied to all components (loaded automatically).

---

## Metrics

The benchmark tracks:

| Metric | Description |
|---|---|
| **Pass Rate** | % of tasks where the agent produced a correct answer |
| **Keyword Match Rate** | % of expected keywords found in responses |
| **Tool Call Recall** | % of expected tools the agent actually called |
| **Tool Call Precision** | % of agent's tool calls that were expected |
| **Tool Call F1** | Harmonic mean of recall and precision |
| **Avg Latency** | Mean time per task (seconds) |

---

## Langfuse Tracing (Optional)

1. Start Langfuse locally:
```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse && docker compose up
```

2. Get keys from the UI at `http://localhost:3000` → Project Settings → API Keys.

3. Add to `.env` and enable in `config/global.env`.

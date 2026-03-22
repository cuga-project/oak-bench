#!/bin/bash

# Script to load environment variables and run cuga viz
# Usage: viz.sh <benchmark_name>
# Example: viz.sh m3

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_DIR="$PROJECT_ROOT/config"
BENCHMARK_NAME="${1:-}"

if [ -z "$BENCHMARK_NAME" ]; then
    echo "Usage: $0 <benchmark_name>"
    echo "Example: $0 m3"
    exit 1
fi

echo "Loading $BENCHMARK_NAME visualization configuration..."

# Load environment variables using helper script
HELPERS_DIR="$PROJECT_ROOT/helpers"
source "$HELPERS_DIR/load_env.sh" "$BENCHMARK_NAME"

echo ""
echo "Running cuga viz..."
cd "$PROJECT_ROOT"
uv run cuga-viz run $CUGA_LOGGING_DIR/trajectory_data/

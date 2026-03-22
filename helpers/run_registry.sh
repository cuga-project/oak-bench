#!/bin/bash

# Generic script to load environment variables and start the registry
# This script loads both global and benchmark-specific configuration

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

echo "Loading $BENCHMARK_NAME evaluation configuration..."

# Load environment variables using helper script
HELPERS_DIR="$SCRIPT_DIR"
source "$HELPERS_DIR/load_env.sh" "$BENCHMARK_NAME"

# Note: The Python scripts will also automatically load config/global.env and config/${BENCHMARK_NAME}.env
# using python-dotenv, but we load them here too so they're available to shell scripts

echo ""
echo "✓ Configuration will be loaded by Python scripts"
echo ""
echo "Starting registry server..."
cd "$PROJECT_ROOT"
uv run registry

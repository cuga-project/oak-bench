#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="git@github.ibm.com:research-rpa/cuga-agent.git"
VENDOR_DIR="./vendor"
REPO_NAME="cuga-agent"
REPO_PATH="${VENDOR_DIR}/${REPO_NAME}"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if git is installed
check_git() {
    if ! command -v git &> /dev/null; then
        print_error "Git is not installed. Please install git and try again."
        exit 1
    fi
}

# Function to create vendor directory if it doesn't exist
create_vendor_dir() {
    if [ ! -d "$VENDOR_DIR" ]; then
        print_status "Creating vendor directory..."
        mkdir -p "$VENDOR_DIR"
        print_success "Vendor directory created"
    fi
}

# Function to clone repository
clone_repo() {
    print_status "Cloning repository from $REPO_URL..."

    if git clone "$REPO_URL" "$REPO_PATH"; then
        print_success "Repository cloned successfully to $REPO_PATH"
        return 0
    else
        print_error "Failed to clone repository. Please check your SSH keys and network connection."
        return 1
    fi
}

# Function to update existing repository
update_repo() {
    print_status "Repository already exists. Pulling latest changes..."
    cd "$REPO_PATH" || exit 1

    if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
        print_success "Repository updated successfully"
    else
        print_warning "Could not update repository. You may need to resolve conflicts manually."
    fi

    cd - > /dev/null || exit 1
}

# Function to export environment variables to current terminal session
export_env_vars() {
    print_status "Exporting environment variables to current terminal session..."

    # Define environment variables to export
    export ENV_FILE="./.env"
    export MCP_SERVERS_FILE="./mcp_servers.yaml"
    export CUGA_LOGGING_DIR="./logging"

    print_status "Exported ENV_FILE=./.env"
    print_status "Exported MCP_SERVERS_FILE=./mcp_servers.yaml"
    print_status "Exported CUGA_LOGGING_DIR=./logging"

    print_success "Environment variables exported to current terminal session"
}

# Function to create logging directory
create_logging_dir() {
    if [ ! -d "./logging" ]; then
        print_status "Creating logging directory..."
        mkdir -p "./logging"
        print_success "Logging directory created"
    fi
}

# Main execution
main() {
    local pull_branch="$1"

    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    CUGA Agent Setup Script                   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Check prerequisites
    check_git

    # Create vendor directory
    create_vendor_dir

    # Clone or update repository
    if [ -d "$REPO_PATH" ]; then
        if [ -d "$REPO_PATH/.git" ]; then
            print_status "Repository already exists at $REPO_PATH"
            update_repo "$pull_branch"
        else
            print_warning "Directory exists but is not a git repository. Removing and cloning fresh..."
            rm -rf "$REPO_PATH"
            clone_repo || exit 1
        fi
    else
        clone_repo || exit 1
    fi

    # Export environment variables to current terminal
    export_env_vars

    # Create logging directory
    create_logging_dir

    echo ""
    print_success "Setup completed successfully!"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Check the cloned repository at: $REPO_PATH"
    echo "  2. Environment variables are now available in this terminal session"
    echo "  3. Note: Variables will only persist for this terminal session"
    echo ""
}

# Run main function
main "$@"
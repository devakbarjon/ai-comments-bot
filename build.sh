#!/bin/bash

# Simple build script for AI Comments Bot deployment

set -e

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 required"
    exit 1
fi

# Check pip3
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 required"
    exit 1
fi

# Set up paths
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

# Create virtual environment if needed or if it's invalid
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Creating virtual environment..."
    # Remove invalid venv if it exists
    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
    fi
    if ! python3 -m venv "$VENV_DIR"; then
        echo "Error: Failed to create virtual environment"
        echo "Please ensure python3-venv package is installed"
        exit 1
    fi
fi

# Activate and install
source "$VENV_DIR/bin/activate"
pip3 install --upgrade pip
pip3 install -r "$PROJECT_DIR/requirements.txt"

# Check for .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

echo "Setup complete. To run:"
echo "  source venv/bin/activate && python3 bot.py"
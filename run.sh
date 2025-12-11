#!/bin/bash

# Wrapper script to run the scraper

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Set PYTHONPATH to include src
export PYTHONPATH=$PYTHONPATH:$(pwd)/src

# Run the scraper
python3 src/main.py

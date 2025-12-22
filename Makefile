# Weather Data Collector - Makefile
#
# Copyright (c) 2025 Darren Soothill
# Email: darren [at] soothill [dot] com
# All rights reserved.

.PHONY: help setup config install start stop restart status logs test uninstall clean venv api-key-info

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin
PIP := $(VENV_BIN)/pip
PYTHON_VENV := $(VENV_BIN)/python
SERVICE_NAME := weather-collector
SERVICE_FILE := $(SERVICE_NAME).service
TIMER_FILE := $(SERVICE_NAME).timer
SYSTEMD_USER_DIR := $(HOME)/.config/systemd/user
CACHE_DIR := /var/lib/weather-collector
CONFIG_FILE := config.yml
CONFIG_SAMPLE := config.sample.yml

help: ## Show this help message
	@echo "Weather Data Collector - Makefile Commands"
	@echo "==========================================="
	@echo ""
	@echo "Setup Commands:"
	@echo "  make setup          - Create virtual environment and install dependencies"
	@echo "  make config         - Create configuration file from template"
	@echo "  make api-key-info   - Show instructions for obtaining Met Office API key"
	@echo ""
	@echo "Installation Commands:"
	@echo "  make install        - Install systemd service and timer (user mode)"
	@echo "  make start          - Enable and start the timer"
	@echo ""
	@echo "Management Commands:"
	@echo "  make stop           - Stop and disable the timer"
	@echo "  make restart        - Restart the timer"
	@echo "  make status         - Show service and timer status"
	@echo "  make logs           - Show recent logs from the service"
	@echo ""
	@echo "Data Collection Commands:"
	@echo "  make test                - Run a single data collection manually"
	@echo "  make import-historical   - Import all available historical data (one-time)"
	@echo ""
	@echo "Cleanup Commands:"
	@echo "  make uninstall      - Remove systemd service and timer"
	@echo "  make clean          - Remove virtual environment and cache"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make setup"
	@echo "  2. make api-key-info  (follow instructions to get API key)"
	@echo "  3. make config        (edit config.yml with your settings)"
	@echo "  4. make test          (verify configuration works)"
	@echo "  5. make import-historical  (optional: import historical data)"
	@echo "  6. make install"
	@echo "  7. make start"
	@echo ""

api-key-info: ## Display instructions for obtaining Met Office API key
	@echo ""
	@echo "╔═══════════════════════════════════════════════════════════════════╗"
	@echo "║         How to Get Your Met Office DataHub API Key              ║"
	@echo "╚═══════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "1. Visit the Met Office DataHub:"
	@echo "   https://datahub.metoffice.gov.uk/"
	@echo ""
	@echo "2. Create an account (or sign in if you already have one):"
	@echo "   - Click 'Sign Up' in the top right"
	@echo "   - Fill in your details and verify your email"
	@echo ""
	@echo "3. Navigate to API Keys:"
	@echo "   - Click on your username in the top right"
	@echo "   - Select 'My Account'"
	@echo "   - Go to 'API Keys' section"
	@echo ""
	@echo "4. Create a new API key:"
	@echo "   - Click 'Create New API Key'"
	@echo "   - Give it a descriptive name (e.g., 'Weather Collector')"
	@echo "   - Select 'Land Observations' API access"
	@echo "   - Copy the generated API key"
	@echo ""
	@echo "5. Add the API key to your config.yml file:"
	@echo "   - Open config.yml in a text editor"
	@echo "   - Find the 'met_office.api_key' field"
	@echo "   - Replace 'YOUR_MET_OFFICE_API_KEY_HERE' with your key"
	@echo ""
	@echo "Note: Keep your API key secure and never commit it to version control!"
	@echo ""

venv: ## Create Python virtual environment
	@echo "Creating Python virtual environment..."
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@echo "Virtual environment created: $(VENV)"

setup: venv ## Setup: Create venv and install dependencies
	@echo "Installing Python dependencies..."
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt
	@echo ""
	@echo "✓ Setup complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run 'make api-key-info' to learn how to get your API key"
	@echo "  2. Run 'make config' to create your configuration file"
	@echo "  3. Edit config.yml with your API keys and settings"
	@echo "  4. Run 'make test' to verify everything works"
	@echo "  5. Run 'make install && make start' to enable the timer"
	@echo ""

config: ## Create config.yml from template
	@if [ -f $(CONFIG_FILE) ]; then \
		echo "⚠ config.yml already exists!"; \
		echo "Delete it first if you want to recreate from template."; \
		exit 1; \
	fi
	@cp $(CONFIG_SAMPLE) $(CONFIG_FILE)
	@echo "✓ Created $(CONFIG_FILE) from template"
	@echo ""
	@echo "IMPORTANT: Edit config.yml and configure:"
	@echo "  1. met_office.api_key - Your Met Office DataHub API key"
	@echo "  2. met_office.location - Coordinates for your location (default: Newport Pagnell)"
	@echo "  3. influxdb.* - Your InfluxDB connection details"
	@echo ""
	@echo "Run 'make api-key-info' for instructions on getting an API key."
	@echo ""

install: ## Install systemd service and timer (user mode)
	@if [ ! -f $(CONFIG_FILE) ]; then \
		echo "✗ Error: config.yml not found!"; \
		echo "Run 'make config' first and configure it."; \
		exit 1; \
	fi
	@if [ ! -d $(VENV) ]; then \
		echo "✗ Error: Virtual environment not found!"; \
		echo "Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Creating cache directory..."
	@sudo mkdir -p $(CACHE_DIR)
	@sudo chown $(USER):$(USER) $(CACHE_DIR)
	@echo "Installing systemd service and timer (user mode)..."
	@mkdir -p $(SYSTEMD_USER_DIR)
	@cp $(SERVICE_FILE) $(SYSTEMD_USER_DIR)/
	@cp $(TIMER_FILE) $(SYSTEMD_USER_DIR)/
	@systemctl --user daemon-reload
	@echo ""
	@echo "✓ Installation complete!"
	@echo ""
	@echo "To start the timer, run: make start"
	@echo ""

start: ## Enable and start the timer
	@echo "Enabling and starting weather collector timer..."
	@systemctl --user enable $(TIMER_FILE)
	@systemctl --user start $(TIMER_FILE)
	@echo ""
	@echo "✓ Weather collector timer started!"
	@echo ""
	@systemctl --user status $(TIMER_FILE) --no-pager
	@echo ""
	@echo "The collector will run hourly. Check status with: make status"
	@echo "View logs with: make logs"
	@echo ""

stop: ## Stop and disable the timer
	@echo "Stopping weather collector timer..."
	@systemctl --user stop $(TIMER_FILE) || true
	@systemctl --user disable $(TIMER_FILE) || true
	@echo "✓ Timer stopped and disabled"

restart: ## Restart the timer
	@echo "Restarting weather collector timer..."
	@systemctl --user restart $(TIMER_FILE)
	@echo "✓ Timer restarted"

status: ## Show service and timer status
	@echo "Weather Collector Status"
	@echo "======================="
	@echo ""
	@echo "Timer Status:"
	@systemctl --user status $(TIMER_FILE) --no-pager || true
	@echo ""
	@echo "Service Status:"
	@systemctl --user status $(SERVICE_FILE) --no-pager || true
	@echo ""
	@echo "Next scheduled runs:"
	@systemctl --user list-timers $(TIMER_FILE) --no-pager || true

logs: ## Show recent logs from the service
	@echo "Recent Weather Collector Logs (last 50 lines)"
	@echo "============================================="
	@journalctl --user -u $(SERVICE_FILE) -n 50 --no-pager

test: ## Run a single data collection manually
	@if [ ! -f $(CONFIG_FILE) ]; then \
		echo "✗ Error: config.yml not found!"; \
		echo "Run 'make config' first and configure it."; \
		exit 1; \
	fi
	@if [ ! -d $(VENV) ]; then \
		echo "✗ Error: Virtual environment not found!"; \
		echo "Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Running weather collector (test mode)..."
	@echo ""
	@$(PYTHON_VENV) weather_collector.py

import-historical: ## Import all available historical weather data (one-time operation)
	@if [ ! -f $(CONFIG_FILE) ]; then \
		echo "✗ Error: config.yml not found!"; \
		echo "Run 'make config' first and configure it."; \
		exit 1; \
	fi
	@if [ ! -d $(VENV) ]; then \
		echo "✗ Error: Virtual environment not found!"; \
		echo "Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Starting historical data import..."
	@echo "This will import all available historical observations from Met Office API"
	@echo ""
	@$(PYTHON_VENV) historical_import.py

uninstall: stop ## Uninstall systemd service and timer
	@echo "Uninstalling weather collector..."
	@rm -f $(SYSTEMD_USER_DIR)/$(SERVICE_FILE)
	@rm -f $(SYSTEMD_USER_DIR)/$(TIMER_FILE)
	@systemctl --user daemon-reload
	@echo "✓ Uninstalled systemd units"
	@echo ""
	@echo "Note: Cache directory $(CACHE_DIR) and config.yml are preserved."
	@echo "To remove them, run: make clean"

clean: ## Remove virtual environment and cache
	@echo "Cleaning up..."
	@rm -rf $(VENV)
	@sudo rm -rf $(CACHE_DIR)
	@echo "✓ Cleaned virtual environment and cache"
	@echo ""
	@echo "Note: config.yml is preserved. Delete manually if needed."

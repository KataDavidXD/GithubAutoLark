"""Pytest configuration and shared fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line("markers", "real_api: mark test as requiring real API access")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--real-api",
        action="store_true",
        default=False,
        help="Run tests that require real API access",
    )


def pytest_collection_modifyitems(config, items):
    """Skip real_api tests unless --real-api flag is provided."""
    if config.getoption("--real-api"):
        return
    
    skip_real = pytest.mark.skip(reason="Need --real-api option to run")
    for item in items:
        if "real_api" in item.keywords:
            item.add_marker(skip_real)

#!/usr/bin/env python
"""Compatibility entry point for the permanent isolated statistics regression."""
from pathlib import Path
import subprocess
import sys
if __name__ == '__main__':
    raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve().parent / 'tests' / 'statistics_frequency_test.py')]))

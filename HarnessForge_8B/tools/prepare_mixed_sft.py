#!/usr/bin/env python3
"""Workspace entry point for the shared mixed-task SFT recipe."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools" / "prepare_mixed_sft.py"), run_name="__main__")

#!/usr/bin/env python3
"""Entry point: python3 scripts/review_tool.py --workspace PATH <command>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review.cli import main

if __name__ == "__main__":
    sys.exit(main())

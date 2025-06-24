#!/usr/bin/env python3
"""
Simple standalone script to set up pitch templates.
Run this from the project root directory.
"""

import asyncio
import os
import sys

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from podcast_outreach.scripts.setup_pitch_templates import main

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
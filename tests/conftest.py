import sys
from pathlib import Path

# Let tests import the fake device helper (tests/fake_voice_pe.py) directly.
sys.path.insert(0, str(Path(__file__).parent))

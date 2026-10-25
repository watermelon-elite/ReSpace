import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent/'reconstruction'))
spec = importlib.util.spec_from_file_location('reconstruction_fixtures',ROOT.parent/'reconstruction/tests/conftest.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
capture = fixtures.capture

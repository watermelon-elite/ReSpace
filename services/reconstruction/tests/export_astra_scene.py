"""Export an offline synthetic response for the Swift native-import test.

From services/reconstruction:
PYTHONPATH=. .venv/bin/python tests/export_astra_scene.py --output /tmp/astra-fixture
"""
import argparse
import os
from pathlib import Path
from unittest.mock import patch

from respace_reconstruction import astra, astra_room
from test_astra_room import response
from test_walkthrough import room_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    folder = parser.parse_args().output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    room_capture(folder)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-test-key", "RESPACE_ASTRA_IMAGE_LIMIT": "5"}), \
            patch.object(astra, "call_astra", return_value=response()):
        astra_room.process_astra_room(folder, 1)
    print(folder/"results/1")


if __name__ == "__main__":
    main()

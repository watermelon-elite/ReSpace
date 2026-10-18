"""Export an offline synthetic response for the Swift native-import test.

From services/reconstruction:
PYTHONPATH=. .venv/bin/python tests/export_astra_scene.py --output /tmp/astra-fixture
"""
import argparse
import os
from pathlib import Path
from unittest.mock import patch

from respace_reconstruction import astra, astra_room, astra_spending
from test_astra_room import response
from test_walkthrough import room_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detailed", action="store_true")
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    room_capture(folder)
    from test_astra_detail import reply, detailed_reply, room_plan
    replies = [reply(room_plan()), detailed_reply()] if args.detailed else [response()]
    with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-test-key", "RESPACE_ASTRA_IMAGE_LIMIT": "5"}), \
            patch.object(astra_spending, "count_input_tokens", return_value=1000), \
            patch.object(astra, "call_astra", side_effect=replies):
        astra_room.process_astra_room(folder, 1, detailed=args.detailed)
    print(folder/"results/1")


if __name__ == "__main__":
    main()

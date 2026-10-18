import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import ORIGINAL_ID, WORKING_ID, ROOT, create_app
from vlog_format.script_export import build_script_export


class ScriptScreenTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "workspace.json"
        self.app = create_app(self.path)
        self.app.testing = True
        self.client = self.app.test_client()
        self.client.get("/")
        self.base = "/runs/respace/packages/respace-launch"

    def state(self):
        return json.loads(self.path.read_text())

    def test_render_complete_story_and_original_screen(self):
        page = self.client.get("/").get_data(as_text=True)
        for lane in ("base", "overlay_1", "overlay_2", "subtitles"):
            self.assertIn(f'data-track-key="{lane}"', page)
        for number in range(1, 44):
            self.assertIn(f"SHOT {number:02}", page)
        self.assertNotIn('class="format-contributors"', page)
        self.assertIn('data-copy-export-button', page)
        old = self.client.get("/?version=" + ORIGINAL_ID).get_data(as_text=True)
        self.assertIn('data-editing-disabled="true"', old)
        current = self.state()["versions"][-1]["content"]
        self.assertEqual(current["script"]["narration"], (ROOT / "data/voiceover.txt").read_text())

    def test_edit_reanchors_without_changing_runtime_or_original(self):
        before = self.state()
        content = before["versions"][-1]["content"]
        block = content["visual_tracks"]["base"][0]
        changed = "Imagine this. " + content["script"]["narration"]
        response = self.client.put(self.base + "/autosave", json={
            "generated_base_version_id": ORIGINAL_ID, "narration": changed,
            "titles": ["ReSpace rehearsal"],
            "visual_edits": [{"id": block["id"], "visual_description": "New camera note", "exact_action": "Keep the doorway wide."}],
        })
        self.assertEqual(response.status_code, 200)
        saved = response.json["content"]
        self.assertEqual(saved["script"]["estimated_duration_seconds"], 180)
        self.assertEqual(self.state()["versions"][0], before["versions"][0])
        ids = {word["id"] for word in saved["script"]["words"]}
        for lane in saved["visual_tracks"].values():
            for visual in lane:
                self.assertIn(visual["start_word_id"], ids)
                self.assertIn(visual["end_word_id"], ids)
        export = build_script_export(title="ReSpace rehearsal", version_id=WORKING_ID, content=saved)
        self.assertIn("New camera note", export["plain_text"])
        self.assertIn("Keep the doorway wide.", export["plain_text"])
        self.assertIn("03:00", export["lines"][-1]["heading"])

    def test_comments_survive_edit_and_can_be_removed(self):
        content = self.state()["versions"][-1]["content"]
        target = content["script"]["beats"][0]["id"] + ":narration:text"
        response = self.client.post(self.base + "/comments", data={
            "comment_text": "Keep the opening pause", "narration_target": target,
            "range_start": 0, "range_end": 4, "version_id": WORKING_ID,
        })
        self.assertEqual(response.status_code, 200)
        comment_id = response.json["comment"]["id"]
        self.assertEqual(response.json["comment"]["anchored_text"], "This")
        response = self.client.put(self.base + "/autosave", json={
            "generated_base_version_id": ORIGINAL_ID,
            "narration": "Imagine. " + content["script"]["narration"], "visual_edits": [],
        })
        self.assertEqual(response.status_code, 200)
        comment = self.state()["feedback"][0]
        self.assertEqual(comment["range_start"], len("Imagine. "))
        self.assertIn("Keep the opening pause", self.client.get("/").get_data(as_text=True))
        url = self.base + "/comments/" + comment_id
        self.assertEqual(self.client.put(url, data={"comment_text": "Hold longer"}).json["comment"]["feedback_text"], "Hold longer")
        self.assertTrue(self.client.put(url, data={"comment_text": ""}).json["deleted"])
        self.assertEqual(self.state()["feedback"], [])

    def test_rejected_edits_preserve_saved_data(self):
        before = self.path.read_bytes()
        self.assertEqual(self.client.put(self.base + "/autosave", json={"generated_base_version_id": ORIGINAL_ID, "narration": ""}).status_code, 400)
        self.assertEqual(self.client.post(self.base + "/comments", data={"comment_text": "Untrusted"}, headers={"Origin": "https://example.com"}).status_code, 403)
        self.assertEqual(self.path.read_bytes(), before)

    def test_export_retains_all_silent_shots(self):
        content = self.state()["versions"][-1]["content"]
        export = build_script_export(title="ReSpace", version_id=WORKING_ID, content=content)
        for number in range(1, 44):
            self.assertEqual(export["plain_text"].count(f"SHOT {number:02} ·"), 1)
        self.assertIn("02:18", export["plain_text"])
        self.assertIn("02:42", export["plain_text"])


if __name__ == "__main__":
    unittest.main()

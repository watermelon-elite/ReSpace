import json
import re
from copy import deepcopy
from html import unescape
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import ORIGINAL_ID, WORKING_ID, ROOT, create_app
from vlog_format.script_export import build_script_export
from vlog_format.production_validation import remap_version_word_anchors
from vlog_format.word_anchors import anchored_text
from seed import build_seed, replace_middle


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
        self.assertIn("Close-up of the standard bed.", page)
        self.assertNotIn('class="format-contributors"', page)
        self.assertIn('data-copy-export-button', page)
        old = self.client.get("/?version=" + ORIGINAL_ID).get_data(as_text=True)
        self.assertIn('data-editing-disabled="true"', old)
        current = self.state()["versions"][-1]["content"]
        self.assertEqual(current["script"]["narration"], (ROOT / "data/voiceover.txt").read_text())
        for blocks in current["visual_tracks"].values():
            for block in blocks:
                text = block["visual_description"] + block["recording_requirement"]["exact_action"].split("\n\n", 1)[0]
                self.assertIsNone(re.search(r"\d{2}:\d{2}|DELIVERY:|PICTURE / ACTION:|SOUND / EDIT:|SOURCE:", text))

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

    def test_export_replaces_old_middle_and_retains_closing(self):
        content = self.state()["versions"][-1]["content"]
        export = build_script_export(title="ReSpace", version_id=WORKING_ID, content=content)
        retained = [shot for block in content["visual_tracks"]["base"] for shot in block["shot_ids"]]
        self.assertTrue(set(retained) <= {shot["id"] for shot in content["storyboard_shots"]})
        self.assertTrue({f"shot-{number:02}" for number in range(44, 48)} <= set(retained))
        self.assertEqual({shot for shot in retained if shot.startswith("shot-middle-")},
                         {f"shot-middle-{number:02}" for number in range(1, 13)})
        self.assertIn("02:42", export["plain_text"])
        self.assertIn("Can I borrow $200? It’s for the vision.", export["plain_text"])
        self.assertIn("Café · Conversation", export["plain_text"])
        self.assertIn("It's still the room you walked into.", export["plain_text"])
        for stale in ("A friend starts to leave.", "Measure / Plan / Check",
                      "Or use it to design your business.", "demo-community", "future-study"):
            self.assertNotIn(stale, export["plain_text"])

    def test_independent_layers_and_speaker_handoff(self):
        content = self.state()["versions"][-1]["content"]
        positions = {word["id"]: index for index, word in enumerate(content["script"]["words"])}
        tracks = content["visual_tracks"]
        for blocks in tracks.values():
            previous_end = -1
            previous_word = -1
            for block in blocks:
                self.assertLessEqual(previous_end, block["start_seconds"])
                self.assertLess(block["start_seconds"], block["end_seconds"])
                self.assertLessEqual(block["end_seconds"], 180)
                self.assertLess(previous_word, positions[block["start_word_id"]])
                previous_end = block["end_seconds"]
                previous_word = positions[block["end_word_id"]]
                self.assertTrue(block["recording_requirement"]["exact_action"])
        presenter = next(block for block in tracks["base"] if block["id"] == "middle-base-03")
        self.assertEqual((presenter["start_seconds"], presenter["end_seconds"]), (32, 42))
        panels = [block for block in tracks["overlay_1"] if block["id"] in
                  {"middle-overlay_1-02", "middle-overlay_1-03", "middle-overlay_1-04"}]
        self.assertEqual(panels[0]["start_seconds"], presenter["start_seconds"])
        self.assertEqual(panels[-1]["end_seconds"], presenter["end_seconds"])
        self.assertEqual([anchored_text(content, panel) for panel in panels[:2]],
                         ["Choose what stays", "Set a budget"])
        question = next(block for block in tracks["base"] if block["id"] == "middle-base-04")
        references = next(block for block in tracks["base"] if block["id"] == "middle-base-05")
        self.assertTrue(anchored_text(content, question).endswith("where does everyone sit"))
        self.assertEqual(anchored_text(content, references), "And which of these spaces feels more like you")
        for lane in ("overlay_1", "overlay_2"):
            self.assertFalse(any(block["start_seconds"] < 121 and block["end_seconds"] > 117
                                 for block in tracks[lane]))
        for beat in content["script"]["beats"]:
            self.assertEqual(beat["speaker"], "External narrator" if beat["start_seconds"] < 24 else "ReSpace team")
        export = build_script_export(title="ReSpace", version_id=WORKING_ID, content=content)
        self.assertIn("External narrator", export["lines"][0]["heading"])
        panel = panels[0]
        response = self.client.put(self.base + "/autosave", json={
            "generated_base_version_id": ORIGINAL_ID, "narration": content["script"]["narration"],
            "visual_edits": [{"id": panel["id"], "exact_action": "Enter beside the presenter after the first sentence."}],
        })
        self.assertEqual(response.status_code, 200)
        saved = next(block for block in response.json["content"]["visual_tracks"]["overlay_1"] if block["id"] == panel["id"])
        self.assertEqual(saved["start_seconds"], 32)
        self.assertEqual(saved["recording_requirement"]["exact_action"], "Enter beside the presenter after the first sentence.")

    def test_middle_matches_approved_html_and_complete_directions(self):
        definition = json.loads((ROOT / "data/middle.json").read_text())
        source = (ROOT.parent / definition["source"]).read_text()
        passages = [unescape(text).strip("“”") for text in re.findall(
            r'<article class="beat".*?<blockquote>(.*?)</blockquote>', source, re.S)]
        self.assertEqual([beat["narration"] for beat in definition["beats"]], passages)
        content = self.state()["versions"][-1]["content"]
        middle = [beat for beat in content["script"]["beats"] if 24 <= beat["start_seconds"] < 162]
        self.assertEqual([anchored_text(content, beat).rstrip(".!?") for beat in middle],
                         [text.rstrip(".!?") for text in passages])
        for beat in definition["beats"]:
            for direction in beat["directions"]:
                self.assertIn(direction, beat["base"][0]["exact_action"])
        base = [b for b in content["visual_tracks"]["base"] if 24 <= b["start_seconds"] < 162]
        self.assertEqual(base[0]["start_seconds"], 24)
        self.assertEqual(base[-1]["end_seconds"], 162)
        self.assertTrue(all(a["end_seconds"] == b["start_seconds"] for a, b in zip(base, base[1:])))

    def test_middle_rebuild_preserves_custom_opening_and_closing(self):
        content = deepcopy(self.state()["versions"][-1]["content"])
        content["script"]["narration"] = "My custom opening. " + content["script"]["narration"] + "My custom closing."
        content = remap_version_word_anchors(content)
        content["visual_tracks"]["base"][0]["visual_description"] = "Custom doorway shot."
        content["visual_tracks"]["base"][-1]["visual_description"] = "Custom end card."
        definition = json.loads((ROOT / "data/middle.json").read_text())
        changed = deepcopy(definition)
        changed["beats"][0]["narration"] += " A little more detail."
        result = replace_middle(content, changed)
        self.assertEqual(result["script"]["estimated_duration_seconds"], 180)
        for key in ("base", "overlay_1", "overlay_2", "beats"):
            def protected(package):
                records = package["script"]["beats"] if key == "beats" else package["visual_tracks"][key]
                return [{**{k: v for k, v in record.items() if k not in ("start_word_id", "end_word_id")},
                         "text": anchored_text(package, record)}
                        for record in records if record["end_seconds"] <= 24 or record["start_seconds"] >= 162]
            self.assertEqual(protected(result), protected(content), key)
        self.assertTrue(result["script"]["narration"].startswith("My custom opening. "))
        self.assertTrue(result["script"]["narration"].endswith("My custom closing."))
        self.assertEqual(build_seed(), json.loads((ROOT / "data/seed.json").read_text()))


if __name__ == "__main__":
    unittest.main()

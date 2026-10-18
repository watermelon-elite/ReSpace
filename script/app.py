"""Local persistence adapter for the copied DS_HQ Script screen."""

from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Flask, abort, jsonify, render_template, request, url_for

from format_workflow.script_presentation import narrative_beat_views, scripts_page_context
from vlog_format.production_validation import remap_version_word_anchors, tokenize_narration

ROOT = Path(__file__).resolve().parent
PACKAGE_ID = "respace-launch"
ORIGINAL_ID = "respace-original"
WORKING_ID = "respace-working"


def now():
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = RLock()

    def read(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        content = json.loads((ROOT / "data/seed.json").read_text())
        created = now()
        original = dict(id=ORIGINAL_ID, number=1, kind="generated", source="import",
                        parent_version_id=None, created_at=created, updated_at=created,
                        content=content)
        working = deepcopy(original)
        working.update(id=WORKING_ID, number=2, kind="working", source="manual",
                       parent_version_id=ORIGINAL_ID)
        working["content"]["version_id"] = WORKING_ID
        working["content"] = remap_version_word_anchors(working["content"])
        state = {"versions": [original, working], "feedback": []}
        self.save(state)
        return state

    def save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(self.path)

    def read_production_packages(self, run_id):
        with self.lock:
            state = self.read()
            return [{"id": PACKAGE_ID, "run_id": "respace",
                     "active_version_id": WORKING_ID, "active_version": state["versions"][-1],
                     "versions": state["versions"]}]

    def read_feedback(self, package_id):
        with self.lock:
            return self.read()["feedback"]


def preserve_comments(comments, old, new):
    matches = SequenceMatcher(None, old, new, autojunk=False).get_matching_blocks()
    for comment in comments:
        if comment["target_type"] != "narration-span":
            continue
        start, end = comment["range_start"], comment["range_end"]
        match = next((m for m in matches if m.a <= start < end <= m.a + m.size), None)
        if match:
            comment["range_start"] = match.b + start - match.a
            comment["range_end"] = match.b + end - match.a
        else:
            # Keep feedback visible when its selected words are replaced or deleted.
            comment.update(target_type="package", target_id=PACKAGE_ID,
                           range_start=None, range_end=None,
                           feedback_text=f"On changed text ‘{comment['anchored_text']}’: {comment['feedback_text']}")


def create_app(state_path=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=2_000_000,
                      TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"])
    repository = Repository(state_path or ROOT / "data/workspace.json")
    app.extensions["repository"] = repository

    @app.before_request
    def local_writes():
        if request.method in {"POST", "PUT", "DELETE"}:
            origin = request.headers.get("Origin")
            if (origin and urlsplit(origin).netloc != request.host) or request.headers.get("Sec-Fetch-Site") == "cross-site":
                abort(403)

    @app.errorhandler(ValueError)
    def invalid_input(error):
        return jsonify(status="failed", error=str(error)), 400

    @app.errorhandler(OSError)
    def storage_error(error):
        app.logger.exception("Workspace could not be read or saved")
        return jsonify(status="failed", error="Workspace could not be saved. Your existing file has been kept."), 500

    def check_target(run_id, package_id):
        if run_id != "respace" or package_id != PACKAGE_ID:
            abort(404)

    @app.get("/")
    @app.get("/runs/<run_id>/scripts")
    def scripts(run_id="respace"):
        if run_id != "respace":
            abort(404)
        with repository.lock:
            context = scripts_page_context(repository, run_id,
                selected_package_id=request.args.get("package"), selected_version_id=request.args.get("version"))
        return render_template("format_workflow/scripts.html", **context,
            run={"id": run_id, "title": "ReSpace launch film", "week_label": "Production script"},
            format_ui={"scripts_endpoint": "scripts", "autosave_package_endpoint": "autosave_package",
                       "add_script_comment_endpoint": "add_script_comment", "edit_script_comment_endpoint": "edit_script_comment"})

    @app.put("/runs/<run_id>/packages/<package_id>/autosave")
    def autosave_package(run_id, package_id):
        check_target(run_id, package_id)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("Autosave requires script edits.")
        if payload.get("generated_base_version_id") != ORIGINAL_ID:
            return jsonify(error="This version is read-only. Reload the working version."), 409
        narration = payload.get("narration")
        if not isinstance(narration, str) or len(narration) > 100_000 or not tokenize_narration(narration, version_id=WORKING_ID):
            raise ValueError("Keep at least one spoken word in the script.")
        titles = payload.get("titles")
        if titles is not None and (not isinstance(titles, list) or not 1 <= len(titles) <= 20 or any(not isinstance(t, str) or not t.strip() or len(t) > 500 for t in titles)):
            raise ValueError("Provide a nonempty script title.")
        edits = payload.get("visual_edits", [])
        if not isinstance(edits, list):
            raise ValueError("Visual edits must be a list.")
        with repository.lock:
            state = repository.read()
            version = state["versions"][-1]
            content = version["content"]
            blocks = {b["id"]: b for lane in content["visual_tracks"].values() for b in lane}
            for edit in edits:
                if not isinstance(edit, dict) or edit.get("id") not in blocks:
                    raise ValueError("Unknown visual block. Reload before editing.")
                block = blocks[edit["id"]]
                for field in ("visual_description", "exact_action"):
                    if field not in edit:
                        continue
                    if not isinstance(edit[field], str) or len(edit[field]) > 30_000:
                        raise ValueError("Visual directions must be text.")
                    if field == "exact_action":
                        if not block.get("recording_requirement"):
                            raise ValueError("This block has no following action.")
                        block["recording_requirement"][field] = edit[field]
                    else:
                        block[field] = edit[field]
            old_narration = content["script"]["narration"]
            content["script"]["narration"] = narration
            if titles is not None:
                content["script"]["titles"] = [t.strip() for t in titles]
            content = remap_version_word_anchors(content)
            content["script"]["estimated_duration_seconds"] = 180
            preserve_comments(state["feedback"], old_narration, narration)
            version.update(content=content, updated_at=now())
            repository.save(state)
        return jsonify(status="saved", version={k: version[k] for k in ("id", "number", "kind", "updated_at")}, content=content)

    @app.post("/runs/<run_id>/packages/<package_id>/comments")
    def add_script_comment(run_id, package_id):
        check_target(run_id, package_id)
        form = request.form
        text = form.get("comment_text", "").strip()
        if not text or len(text) > 10_000:
            raise ValueError("Enter a comment of up to 10,000 characters.")
        if form.get("version_id", WORKING_ID) != WORKING_ID:
            return jsonify(error="Comments cannot be added to the original version."), 409
        with repository.lock:
            state = repository.read()
            content = state["versions"][-1]["content"]
            comment = dict(id=uuid4().hex, package_id=PACKAGE_ID, version_id=WORKING_ID,
                           target_type="package", target_id=PACKAGE_ID, target_state="valid",
                           range_start=None, range_end=None, anchored_text="", feedback_text=text,
                           is_commentary=True, created_at=now())
            visual, subtitle, narration = (form.get(k) for k in ("visual_target", "subtitle_target", "narration_target"))
            if sum(bool(v) for v in (visual, subtitle, narration)) > 1:
                raise ValueError("Select one comment target.")
            if visual or subtitle:
                items = [b for lane in content["visual_tracks"].values() for b in lane] if visual else content["subtitle_directives"]
                if (visual or subtitle) not in {b["id"] for b in items}:
                    raise ValueError("The selected block no longer exists.")
                comment.update(target_type="visual-block" if visual else "subtitle-directive", target_id=visual or subtitle)
            elif narration:
                beats = {b["id"] + ":narration:text": b for b in narrative_beat_views(content)}
                end_target = form.get("range_end_target") or narration
                if narration not in beats or end_target not in beats:
                    raise ValueError("Select text from the current script.")
                try:
                    start, end = int(form.get("range_start", "")), int(form.get("range_end", ""))
                except ValueError:
                    raise ValueError("Select a valid text range.") from None
                first, last = beats[narration], beats[end_target]
                if not (0 <= start < len(first["narration_text"]) and 0 < end <= len(last["narration_text"])):
                    raise ValueError("The selection has changed. Select it again.")
                start, end = first["start_char"] + start, last["start_char"] + end
                if start >= end:
                    raise ValueError("Select a nonempty text range.")
                comment.update(target_type="narration-span", range_start=start, range_end=end,
                               anchored_text=content["script"]["narration"][start:end])
            state["feedback"].append(comment)
            repository.save(state)
        return jsonify(status="saved", comment=comment, edit_url=url_for("edit_script_comment", run_id=run_id, package_id=package_id, feedback_id=comment["id"]))

    @app.put("/runs/<run_id>/packages/<package_id>/comments/<feedback_id>")
    def edit_script_comment(run_id, package_id, feedback_id):
        check_target(run_id, package_id)
        text = request.form.get("comment_text", "").strip()
        if len(text) > 10_000:
            raise ValueError("Comment is too long.")
        with repository.lock:
            state = repository.read()
            comment = next((c for c in state["feedback"] if c["id"] == feedback_id), None)
            if comment is None:
                abort(404)
            if text:
                comment["feedback_text"] = text
            else:
                state["feedback"].remove(comment)
            repository.save(state)
        return jsonify(status="saved" if text else "deleted", deleted=not text, comment=comment if text else None)

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5190)
    args = parser.parse_args()
    create_app().run(host="127.0.0.1", port=args.port, debug=False)

"""Clip audio presence must be recorded at asset time, not discovered later.

Two failures in one production run share a root cause: nothing recorded
which picked clips carried an audio stream.

- The edit director planned four L-cuts. Five of the thirteen picks had
  no audio at all, so none of the welds could be performed and they were
  dropped with a warning at compose time.
- The same absence made the approved music dropout flatline the whole
  track, because there was no bed under the music to fall back to.

Both were discoverable at the asset stage with one `ffprobe` call per
clip, and both were only noticed after delivery. `asset_manifest` had no
field to record it in — the assets items are closed
(`additionalProperties: false`) — so even a diligent agent had nowhere
to put the answer.
"""

import json
from pathlib import Path

import pytest

from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skills" / "pipelines" / "documentary-montage"


def _skill(name: str) -> str:
    return (SKILL_DIR / f"{name}.md").read_text(encoding="utf-8")


def test_asset_manifest_can_record_audio_presence():
    schema = json.loads(
        (ROOT / "schemas" / "artifacts" / "asset_manifest.schema.json")
        .read_text(encoding="utf-8")
    )
    props = schema["properties"]["assets"]["items"]["properties"]
    assert "has_audio" in props, (
        "asset_manifest assets are closed and cannot record whether a clip "
        "has an audio stream, so the edit director has to guess"
    )


def test_a_manifest_recording_has_audio_validates():
    manifest = {
        "version": "1.0",
        "assets": [{
            "id": "asset_slot_01",
            "type": "video",
            "path": "projects/x/assets/video/raw/clips/c.mp4",
            "source_tool": "direct_clip_search",
            "scene_id": "slot_01",
            "duration_seconds": 12.0,
            "has_audio": False,
            "resolution": "1920x1080",
        }],
    }
    validate_artifact("asset_manifest", manifest)


def test_asset_director_tells_the_agent_to_probe_for_audio():
    text = _skill("asset-director")
    assert "has_audio" in text, "asset-director never mentions has_audio"
    assert "select_streams a" in text, (
        "asset-director should give the concrete ffprobe invocation"
    )


def test_asset_director_says_to_surface_an_all_silent_pick_set():
    """It constrains the edit, so it belongs in the checkpoint summary."""
    text = _skill("asset-director").lower()
    assert "checkpoint summary" in text


@pytest.mark.parametrize("requirement", ["has_audio", "l-cut"])
def test_edit_director_gates_l_cuts_on_audio(requirement):
    text = _skill("edit-director").lower()
    assert requirement.lower() in text, (
        f"edit-director's L-cut guidance does not reference {requirement}"
    )


def test_edit_director_links_silent_picks_to_the_dropout_decision():
    """The two failures share a cause; the guidance should say so."""
    text = _skill("edit-director").lower()
    assert "no bed underneath" in text or "no bed under" in text, (
        "edit-director should connect silent picks to the music-dropout "
        "decision, not just to L-cuts"
    )

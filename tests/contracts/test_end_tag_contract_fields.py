"""The documentary-montage end-tag contract must be expressible in artifacts.

Three sources agree that the end-tag lives at the top level of the artifacts:

- `skills/pipelines/documentary-montage/edit-director.md` section 8b writes
  `edit_decisions.end_tag`,
- `skills/pipelines/documentary-montage/compose-director.md` reads
  `edit_decisions.end_tag.offset_seconds`,
- `pipeline_defs/documentary-montage.yaml` gates on
  `end_tag.offset_seconds in edit_decisions` and on
  `render_report.end_tag_rendered` / `end_tag_mode` / `music_mixed`.

The schemas were the outlier: both set `additionalProperties: false` and
declared none of those fields, so an agent that followed the skills produced
artifacts that could not validate, and a compose stage that satisfied the
manifest's success_criteria could not be written at all.
"""

import json
from pathlib import Path

import pytest

from schemas.artifacts import validate_artifact


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "artifacts"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def test_edit_decisions_declares_end_tag():
    props = _schema("edit_decisions")["properties"]
    assert "end_tag" in props, (
        "edit-director.md section 8b writes edit_decisions.end_tag, but the "
        "schema forbids unknown keys and does not declare it"
    )


def test_render_report_declares_manifest_success_criteria_fields():
    props = _schema("render_report")["properties"]
    for field in ("end_tag_rendered", "end_tag_mode", "music_mixed"):
        assert field in props, (
            f"documentary-montage.yaml success_criteria require "
            f"render_report.{field}, but the schema forbids unknown keys and "
            f"does not declare it"
        )


def test_edit_decisions_with_documented_end_tag_validates():
    """The exact shape edit-director.md tells the agent to write."""
    artifact = {
        "version": "1.0",
        "render_runtime": "remotion",
        "renderer_family": "documentary-montage",
        "cuts": [
            {"id": "cut_01", "source": "asset_slot_01",
             "in_seconds": 0.0, "out_seconds": 4.0}
        ],
        "end_tag": {
            "offset_seconds": 84.5,
            "mode": "overlay",
            "text": "WE BUILT BOTH WITH THE SAME HANDS.",
            "palette": "warm_ivory_on_black",
            "duration_seconds": 5.5,
            "component": "EndTag",
            "render_engine": "remotion",
            "notes": "Tag fade-out aligns with the body's closing fade.",
        },
    }
    validate_artifact("edit_decisions", artifact)


def test_render_report_with_documented_end_tag_fields_validates():
    """A compose stage that satisfies the manifest's success_criteria."""
    artifact = {
        "version": "1.0",
        "outputs": [{
            "path": "projects/x/renders/final.mp4",
            "format": "mp4",
            "resolution": "1920x1080",
            "duration_seconds": 75.0,
        }],
        "end_tag_rendered": True,
        "end_tag_mode": "overlay",
        "music_mixed": True,
    }
    validate_artifact("render_report", artifact)


def test_end_tag_mode_is_constrained():
    """Only the two modes the compose director implements are legal."""
    import jsonschema

    base = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [{"id": "c1", "source": "a", "in_seconds": 0.0, "out_seconds": 1.0}],
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("edit_decisions", dict(base, end_tag={"mode": "crossfade"}))


def test_end_tag_rejects_unknown_keys():
    """The block is closed, so typos surface instead of being silently kept."""
    import jsonschema

    base = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [{"id": "c1", "source": "a", "in_seconds": 0.0, "out_seconds": 1.0}],
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact(
            "edit_decisions", dict(base, end_tag={"offest_seconds": 69.0})
        )

"""Every documentary-montage shape needs a legal `narrative_structure`.

`proposal_packet.narrative_structure` is a closed enum that was written
for explainers: analogy, problem_solution, journey, debate,
myth_busting, timeline, comparison, tutorial, story, data_narrative.

documentary-montage's idea-director offers four shapes — list/catalogue,
single-image expansion, before/after, three-act. Two of them had no
representable value, so an agent emitting a proposal_packet for a
montage had to squash `list` (accumulation, explicitly no arc) into
`story` (which implies an arc). That is lossy in a governance artifact
whose whole job is recording what was decided and why.

compose-director tells the agent to pass a proposal_packet to
`video_compose` so the runtime-swap check runs actively instead of
reporting `skipped`, so this is not an optional artifact for this
pipeline even though it has no proposal stage.
"""

import json
import re
from pathlib import Path

import pytest

from schemas.artifacts import validate_artifact


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "artifacts" / "proposal_packet.schema.json"
IDEA_DIRECTOR = (
    ROOT / "skills" / "pipelines" / "documentary-montage" / "idea-director.md"
)

# The four shapes the idea-director offers, and the value each maps to.
SHAPE_MAP = {
    "list/catalogue": "list",
    "single-image expansion": "single_image_expansion",
    "before/after": "comparison",
    "three-act": "story",
}


def _enum() -> list[str]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    item = schema["properties"]["concept_options"]["items"]
    return item["properties"]["narrative_structure"]["enum"]


def _concept(structure: str) -> dict:
    return {
        "id": "c1",
        "title": "T",
        "hook": "H",
        "narrative_structure": structure,
        "visual_approach": "V",
        "target_duration_seconds": 75,
        "why_this_works": "W",
    }


@pytest.mark.parametrize("shape,structure", sorted(SHAPE_MAP.items()))
def test_every_montage_shape_has_a_legal_value(shape, structure):
    assert structure in _enum(), (
        f"documentary-montage shape {shape!r} maps to {structure!r}, which "
        f"proposal_packet.narrative_structure does not allow"
    )


@pytest.mark.parametrize("shape,structure", sorted(SHAPE_MAP.items()))
def test_idea_director_documents_the_mapping(shape, structure):
    """The mapping must be written down, not rediscovered per run."""
    text = IDEA_DIRECTOR.read_text(encoding="utf-8")
    row = re.search(
        rf"\|\s*{re.escape(shape)}\s*\|\s*`{re.escape(structure)}`\s*\|", text
    )
    assert row, f"idea-director.md does not map {shape!r} to `{structure}`"


def test_a_montage_proposal_packet_validates():
    """A list-shaped montage must produce a valid artifact."""
    packet = {
        "version": "1.0",
        "concept_options": [
            _concept("list"),
            dict(_concept("comparison"), id="c2"),
            dict(_concept("single_image_expansion"), id="c3"),
        ],
        "selected_concept": {"concept_id": "c1", "rationale": "R"},
        "production_plan": {
            "pipeline": "documentary-montage",
            "render_runtime": "remotion",
            "stages": [
                {"stage": "compose", "approach": "A",
                 "tools": [{"tool_name": "video_compose", "role": "render",
                            "available": True}]}
            ],
        },
        "cost_estimate": {
            "total_estimated_usd": 0.0,
            "budget_verdict": "within_budget",
            "line_items": [
                {"tool": "video_compose", "operation": "render",
                 "estimated_usd": 0.0}
            ],
        },
        "approval": {"status": "approved"},
    }
    validate_artifact("proposal_packet", packet)


def test_explainer_values_are_preserved():
    """Widening the enum must not drop what explainer pipelines already use."""
    enum = _enum()
    for value in ("analogy", "problem_solution", "journey", "debate",
                  "myth_busting", "timeline", "comparison", "tutorial",
                  "story", "data_narrative"):
        assert value in enum, f"enum lost explainer value {value!r}"


def test_enum_stays_closed():
    """An invented value must still be rejected."""
    import jsonschema

    packet = {
        "version": "1.0",
        "concept_options": [_concept("montage_vibes")],
        "selected_concept": {"concept_id": "c1", "rationale": "R"},
        "production_plan": {"pipeline": "p", "render_runtime": "ffmpeg",
                            "stages": []},
        "cost_estimate": {"total_estimated_usd": 0.0,
                          "budget_verdict": "within_budget", "line_items": []},
        "approval": {"status": "approved"},
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("proposal_packet", packet)

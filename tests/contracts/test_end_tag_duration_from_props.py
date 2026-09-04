"""The end-tag's length must follow its timing props.

`EndTag` builds its opacity envelope as `fadeIn -> hold -> fadeOut`, but
both compositions hardcoded `durationInFrames`. Overriding the timings
via `--props` changed the animation while the composition kept its
original length, so the render was padded with transparent (overlay) or
blank (concat) frames.

The compose-director made this worse by documenting
`--props '{"durationInFrames": 132}'`. That is not a component prop and
never had any effect, so an agent asking for a 5.5s card at 24fps still
got the composition's hardcoded default.

Overlay mode tolerates the mismatch — surplus transparent frames fall
past the body and are dropped by `eof_action=pass`. **Concat mode does
not**: the card is appended, so its length lands directly in the
delivered runtime.

`Root.tsx` now derives duration via `calculateEndTagMetadata`. These
tests are static checks on the wiring and the docs; the behaviour itself
was verified by rendering (180 frames for 1.0+3.5+1.5s overlay, 120 for
0.5+2.5+1.0s concat).
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ROOT_TSX = ROOT / "remotion-composer" / "src" / "Root.tsx"
COMPOSE_DIRECTOR = (
    ROOT / "skills" / "pipelines" / "documentary-montage" / "compose-director.md"
)


def _root_tsx() -> str:
    return ROOT_TSX.read_text(encoding="utf-8")


def _composition_block(source: str, composition_id: str) -> str:
    """Return the <Composition .../> block for one id."""
    start = source.index(f'id="{composition_id}"')
    end = source.index("/>", start)
    return source[start:end]


def test_calculate_end_tag_metadata_exists():
    assert "calculateEndTagMetadata" in _root_tsx(), (
        "Root.tsx has no calculateEndTagMetadata; end-tag duration is not "
        "derived from its timing props"
    )


@pytest.mark.parametrize("composition_id", ["EndTag", "EndTagOverlay"])
def test_both_end_tag_compositions_derive_duration(composition_id):
    block = _composition_block(_root_tsx(), composition_id)
    assert "calculateMetadata={calculateEndTagMetadata}" in block, (
        f"{composition_id} does not use calculateEndTagMetadata, so "
        f"--props timings will not change its length"
    )


def test_metadata_sums_the_three_timings():
    """Guard the arithmetic against drifting from the component's envelope."""
    source = _root_tsx()
    start = source.index("calculateEndTagMetadata")
    body = source[start:source.index("export const Root", start)]

    for prop in ("fadeInSeconds", "holdSeconds", "fadeOutSeconds"):
        assert prop in body, f"duration calculation ignores {prop}"
    assert "Math.round" in body, (
        "should mirror the component's per-segment rounding"
    )


def test_compose_director_no_longer_passes_duration_in_frames():
    """The documented CLI must not advertise a prop that does nothing."""
    text = COMPOSE_DIRECTOR.read_text(encoding="utf-8")
    in_props = re.search(r'--props=[^\n]*durationInFrames', text)
    assert not in_props, (
        "compose-director still documents durationInFrames inside --props; "
        "it is not a component prop and has no effect"
    )


def test_compose_director_documents_the_timing_props():
    """It must tell the agent which props actually set the length."""
    text = COMPOSE_DIRECTOR.read_text(encoding="utf-8")
    for prop in ("fadeInSeconds", "holdSeconds", "fadeOutSeconds"):
        assert prop in text, f"compose-director never mentions {prop}"

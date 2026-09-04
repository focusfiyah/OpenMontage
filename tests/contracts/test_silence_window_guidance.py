"""The silence-window and audio-verification guidance must stay in the skills.

Two failures from one production run motivate these checks:

1. The edit-director said "drop the music out for ~2s… use it hard",
   which assumes a documentary mix with ambient under the music. The
   common case here is a music-only bed — `video_compose` renders silent
   and stock clips frequently carry no audio at all — so dropping to zero
   flatlines the entire track. Digital silence mid-film reads as a broken
   file, not a rest.

2. The compose-director treated `music_mixed = true` as something the
   agent asserts. A render returned `success=True` with a valid AAC
   stream that was silent end to end (-91 dB), and every schema and
   success-criterion in the pipeline passed.

These are static checks on the guidance, not behaviour tests.
"""

from pathlib import Path

import pytest


SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills" / "pipelines" / "documentary-montage"
)


def _skill(name: str) -> str:
    return (SKILL_DIR / f"{name}.md").read_text(encoding="utf-8")


def test_edit_director_warns_against_cutting_music_to_zero():
    text = _skill("edit-director").lower()
    assert "duck, do not cut to zero" in text, (
        "edit-director no longer warns that a music-only bed flatlines when "
        "the silence window cuts to zero"
    )


def test_edit_director_explains_when_a_full_cut_is_safe():
    """The rule needs its exception, or it becomes cargo cult."""
    text = _skill("edit-director").lower()
    assert "floor" in text and "ambient" in text, (
        "edit-director should say a full cut is fine when ambient or an "
        "L-cut provides a floor"
    )


def test_edit_director_names_the_deep_duck_mode():
    assert "deep_duck" in _skill("edit-director"), (
        "the recorded metadata.silence_window mode is not documented"
    )


def test_compose_director_requires_measuring_the_mix():
    text = _skill("compose-director")
    assert "volumedetect" in text, (
        "compose-director does not tell the agent to measure the audio; "
        "a silent render passes every other gate in this pipeline"
    )


def test_compose_director_names_the_silence_flatline_value():
    """-91 dB is the tell. Without the number the check is vague."""
    assert "-91 dB" in _skill("compose-director")


@pytest.mark.parametrize("requirement", [
    "windows",          # a short dropout averages away across the whole file
    "tail fade",        # tools override fade_out_seconds at segment boundaries
    "-c:v copy",        # re-mix without re-encoding the graded picture
])
def test_compose_director_covers_the_verification_details(requirement):
    assert requirement in _skill("compose-director").lower(), (
        f"compose-director's audio verification omits: {requirement}"
    )

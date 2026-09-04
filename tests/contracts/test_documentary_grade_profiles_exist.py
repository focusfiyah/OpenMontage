"""Grade profiles named in the director skills must exist in `color_grade`.

The compose-director documented four LUT profiles — `warm_film_100`,
`cool_archive_60`, `neutral_doc_20`, `bleach_bypass_80` — and the
edit-director told the agent to write one of them into
`edit_decisions.metadata.grade_profile`. None of the four existed
anywhere in the repo, and neither did the documented fallback
(`neutral_doc_20`), so the "if the profile isn't in the styles library"
escape hatch pointed at another name that also did not exist.

`color_grade` validates `profile` against its own enum, so an agent that
followed the skill either got a rejected call or silently skipped the
register-smoothing pass that the skill calls "the whole point".

This test parses the skills and asserts every profile name they mention
is real, so the docs cannot drift away from the tool again.
"""

import re
from pathlib import Path

import pytest

from tools.enhancement.color_grade import PROFILES


SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills" / "pipelines" / "documentary-montage"
)

# `grade_profile: "x"`, `"grade_profile": "x"` and bare ``x`` table cells.
_JSON_VALUE = re.compile(r'"grade_profile"\s*:\s*"([^"]+)"')
_TABLE_CELL = re.compile(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|", re.MULTILINE)


def _skill(name: str) -> str:
    return (SKILL_DIR / f"{name}.md").read_text(encoding="utf-8")


def test_color_grade_still_exposes_the_documented_profiles():
    """Guard the names the skills now reference."""
    for expected in ("vintage_film", "cinematic_warm", "cinematic_cool",
                     "moody_dark", "high_contrast", "bright_clean", "neutral"):
        assert expected in PROFILES, f"color_grade lost profile {expected!r}"


@pytest.mark.parametrize("skill", ["compose-director", "edit-director"])
def test_grade_profile_json_values_are_real(skill):
    """Every `"grade_profile": "..."` in an example must be a real profile."""
    for value in _JSON_VALUE.findall(_skill(skill)):
        assert value in PROFILES, (
            f"{skill}.md documents grade_profile {value!r}, which color_grade "
            f"does not implement. Legal values: {sorted(PROFILES)}"
        )


def test_compose_director_profile_table_lists_only_real_profiles():
    """The routing table is what an agent reads to choose; it must be true."""
    text = _skill("compose-director")
    start = text.index("### 3. Apply Grade")
    section = text[start:text.index("### 4.", start)]

    named = set(_TABLE_CELL.findall(section))
    assert named, "no profile table found in the compose-director grade section"

    unknown = named - set(PROFILES)
    assert not unknown, (
        f"compose-director's grade table names profiles that do not exist: "
        f"{sorted(unknown)}"
    )


def test_documented_fallback_profile_exists():
    """The 'if the profile isn't known' escape hatch must point somewhere real."""
    text = _skill("compose-director")
    start = text.index("### 3. Apply Grade")
    section = text[start:text.index("### 4.", start)]

    assert "fall back to" in section.lower(), "no fallback documented"
    # The fallback names a profile in backticks on the same or next line.
    fallback = re.search(r"fall back to\s*\n?\s*`([a-z_]+)`", section, re.IGNORECASE)
    assert fallback, "fallback profile is not named in backticks"
    assert fallback.group(1) in PROFILES, (
        f"documented fallback {fallback.group(1)!r} does not exist in color_grade"
    )

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Matches a decision_log category literal as the instruction docs write it:
# `category: "approval_policy"` or `category="visual_accuracy_check"`, with or
# without surrounding backticks.
_CATEGORY_LITERAL = re.compile(r"""category[`"]?[:=] ?[`"]([a-z_]+)""")


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _instruction_docs() -> list[Path]:
    """Every markdown file an agent is expected to follow."""
    docs = [REPO_ROOT / "AGENT_GUIDE.md"]
    for subdir in ("skills", "docs"):
        docs.extend(sorted((REPO_ROOT / subdir).rglob("*.md")))
    return docs


def _schema_category_enum() -> list[str]:
    schema = json.loads(
        (REPO_ROOT / "schemas/artifacts/decision_log.schema.json").read_text(
            encoding="utf-8"
        )
    )
    return schema["properties"]["decisions"]["items"]["properties"]["category"]["enum"]


def test_music_plans_discover_all_music_capabilities() -> None:
    instruction_files = [
        "AGENT_GUIDE.md",
        "skills/pipelines/cinematic/idea-director.md",
        "skills/pipelines/cinematic/proposal-director.md",
        "skills/pipelines/documentary-montage/idea-director.md",
        "skills/pipelines/explainer/proposal-director.md",
    ]

    for relative_path in instruction_files:
        text = _read(relative_path)
        for capability in ("music_library", "music_search", "music_generation"):
            assert f'get_by_capability("{capability}")' in text, (
                f"{relative_path} omits the {capability!r} music source"
            )


def test_explainer_directors_do_not_reference_fictitious_submit_functions() -> None:
    for stage in ("idea", "script", "scene"):
        text = _read(f"skills/pipelines/explainer/{stage}-director.md")
        assert "handle_explainer_" not in text


def test_instruction_decision_categories_exist_in_schema() -> None:
    """Every decision_log category the instructions name must validate.

    An agent that follows the guide literally writes the category it was told
    to write. If that value is missing from the schema enum, the decision_log
    fails validation and ``write_checkpoint`` rejects the entire checkpoint --
    so the audit trail silently loses the very decision the guide called
    mandatory. This guards that drift in the direction it actually breaks:
    docs naming a category the schema does not accept.
    """
    allowed = set(_schema_category_enum())
    offenders: list[str] = []

    for path in _instruction_docs():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            # Scope to lines that are actually talking about decisions. Other
            # docs use "category" for unrelated things (e.g. Pexels stock
            # categories in skills/creative/stock-sourcing-usage.md).
            if "decision" not in line.lower():
                continue
            for category in _CATEGORY_LITERAL.findall(line):
                if category not in allowed:
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    offenders.append(f"{rel}:{lineno} names category {category!r}")

    assert not offenders, (
        "Instruction docs name decision_log categories that "
        "schemas/artifacts/decision_log.schema.json rejects:\n  "
        + "\n  ".join(offenders)
        + "\nAdd the category to the schema enum, or correct the instructions."
    )

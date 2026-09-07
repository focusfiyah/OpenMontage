"""`encode` must be able to guarantee a file size, not just a quality level.

A documentary master routinely cannot reach the person who commissioned
it: chat and mobile transfer refuse files over ~30 MiB, and a 75s 1080p
render at documentary bitrate lands near 77 MiB. The delivered montage
hit exactly that and had to be hand-encoded with a two-pass ffmpeg
invocation outside the toolchain.

`encode` only exposed CRF, which controls quality and cannot guarantee a
size — you find out whether it fit after spending the encode. `max_size_mb`
switches to two-pass bitrate targeting so the result fits on the first
attempt.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.video.video_compose import VideoCompose


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _run(command: list[str]) -> None:
    subprocess.run(command, capture_output=True, check=True, timeout=120)


@pytest.fixture
def source(tmp_path) -> Path:
    """A clip busy enough that CRF alone would not land on a size."""
    out = tmp_path / "src.mp4"
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=6:r=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
        "-c:a", "aac", "-pix_fmt", "yuv420p", str(out),
    ])
    return out


def test_max_size_mb_is_declared_in_the_schema():
    props = VideoCompose().get_info()["input_schema"]["properties"]
    assert "max_size_mb" in props, (
        "encode cannot express a size cap, so a delivery limit can only be "
        "hit by guessing a CRF and re-encoding"
    )


def test_encode_respects_the_size_cap(source, tmp_path):
    out = tmp_path / "capped.mp4"
    cap = 0.5

    result = VideoCompose().execute({
        "operation": "encode",
        "input_path": str(source),
        "output_path": str(out),
        "max_size_mb": cap,
        "preset": "ultrafast",
    })

    assert result.success, result.error
    assert out.is_file()
    actual = out.stat().st_size / 1048576
    assert actual <= cap, f"produced {actual:.2f} MiB against a {cap} MiB cap"
    assert result.data["within_target"] is True
    assert result.data["mode"] == "two_pass_size_target"


def test_duration_and_streams_survive_the_size_target(source, tmp_path):
    """A size cap is a bitrate change, not a trim or a downscale."""
    out = tmp_path / "capped.mp4"
    VideoCompose().execute({
        "operation": "encode", "input_path": str(source),
        "output_path": str(out), "max_size_mb": 0.5, "preset": "ultrafast",
    })

    def probe(path, entries):
        return subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", entries,
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()

    assert probe(out, "stream=codec_type").count("video") == 1
    assert "audio" in probe(out, "stream=codec_type")
    before = float(probe(source, "format=duration"))
    after = float(probe(out, "format=duration"))
    assert abs(after - before) < 0.5, f"duration drifted: {before} -> {after}"


def test_impossible_cap_fails_with_a_useful_message(source, tmp_path):
    """Better to refuse than to emit something that misses the cap anyway."""
    result = VideoCompose().execute({
        "operation": "encode", "input_path": str(source),
        "output_path": str(tmp_path / "tiny.mp4"), "max_size_mb": 0.02,
    })
    assert not result.success
    assert "too small" in result.error


def test_two_pass_logs_are_cleaned_up(source, tmp_path):
    """The passlog is an implementation detail, not an artifact."""
    out = tmp_path / "capped.mp4"
    VideoCompose().execute({
        "operation": "encode", "input_path": str(source),
        "output_path": str(out), "max_size_mb": 0.5, "preset": "ultrafast",
    })
    leftovers = [p.name for p in tmp_path.iterdir() if "2pass" in p.name]
    assert not leftovers, f"left passlog files behind: {leftovers}"


def test_crf_path_is_unchanged_without_a_cap(source, tmp_path):
    """Existing callers must keep their behaviour."""
    out = tmp_path / "plain.mp4"
    result = VideoCompose().execute({
        "operation": "encode", "input_path": str(source),
        "output_path": str(out), "crf": 30, "preset": "ultrafast",
    })
    assert result.success, result.error
    assert result.data["crf"] == 30
    assert "mode" not in result.data

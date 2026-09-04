"""Regression tests for music declared in edit_decisions.

`video_compose` used to mux audio ONLY from the `audio_path` input, so a
music bed recorded at `edit_decisions.audio.music` — exactly where both
documentary-montage director skills say to put it — was silently dropped
and the render came out with a fully silent audio track (-91 dB). On a
pipeline where music is mandatory that is the worst failure mode
available: it validates, it plays, and it is wrong.
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
    subprocess.run(command, capture_output=True, check=True, timeout=60)


def _mean_volume(path: Path, start: float | None = None, dur: float | None = None) -> float:
    cmd = ["ffmpeg", "-hide_banner"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", str(path), "-map", "0:a", "-af", "volumedetect", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    raise AssertionError(f"volumedetect produced no mean_volume for {path}")


@pytest.fixture
def video(tmp_path) -> Path:
    out = tmp_path / "body.mp4"
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=10:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ])
    return out


@pytest.fixture
def music(tmp_path) -> Path:
    out = tmp_path / "bed.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", str(out)])
    return out


def test_music_from_asset_id_is_resolved_not_dropped(video, music):
    """The bug: a bed at audio.music with an asset_id rendered silent."""
    ed = {"audio": {"music": {"asset_id": "asset_music_bed", "volume": 0.7}}}
    manifest = {"assets": [{"id": "asset_music_bed", "type": "music", "path": str(music)}]}

    track, err, is_temp = VideoCompose()._resolve_audio_for_render(
        {"asset_manifest": manifest}, ed, video
    )

    assert err is None, err
    assert track is not None, "music declared in edit_decisions was dropped"
    assert is_temp
    assert Path(track).is_file()


def test_top_level_music_block_is_also_honored(video, music):
    """edit_decisions.schema.json allows `music` at top level as well."""
    ed = {"music": {"path": str(music), "volume": 0.5}}
    track, err, _ = VideoCompose()._resolve_audio_for_render({}, ed, video)
    assert err is None, err
    assert track is not None


def test_muxed_output_is_actually_audible(video, music):
    """End-to-end: the rendered file must not be digital silence."""
    ed = {"audio": {"music": {"path": str(music), "volume": 0.7}}}
    track, err, _ = VideoCompose()._resolve_audio_for_render({}, ed, video)
    assert err is None, err

    assert VideoCompose()._mux_external_audio(video, track).success
    # Digital silence measures about -91 dB; a real bed sits far above it.
    assert _mean_volume(video) > -60.0


def test_silence_window_is_applied(video, music):
    """The approved silence window must be a real dropout, not a doc comment."""
    ed = {
        "audio": {"music": {"path": str(music), "volume": 0.8}},
        "metadata": {"silence_window": {"start_seconds": 4.0, "end_seconds": 7.0}},
    }
    track, err, _ = VideoCompose()._resolve_audio_for_render({}, ed, video)
    assert err is None, err
    assert VideoCompose()._mux_external_audio(video, track).success

    playing = _mean_volume(video, start=1.0, dur=2.0)
    silent = _mean_volume(video, start=4.5, dur=2.0)
    assert silent < playing - 20.0, f"window not gated: {silent} vs {playing}"


def test_unresolvable_asset_id_fails_loudly(video):
    """A declared bed that cannot be found must error, never render silent."""
    ed = {"audio": {"music": {"asset_id": "asset_missing"}}}
    manifest = {"assets": [{"id": "asset_other", "path": "nope.mp3"}]}

    track, err, _ = VideoCompose()._resolve_audio_for_render(
        {"asset_manifest": manifest}, ed, video
    )

    assert track is None
    assert err and "asset_missing" in err


def test_explicit_audio_path_still_wins(video, music):
    """Backward compatibility: callers passing audio_path keep their behavior."""
    ed = {"audio": {"music": {"path": str(music)}}}
    track, err, is_temp = VideoCompose()._resolve_audio_for_render(
        {"audio_path": str(music)}, ed, video
    )
    assert err is None
    assert Path(track) == music
    assert not is_temp, "an explicit path must not be treated as a temp file"


def test_no_music_block_is_not_an_error(video):
    """Pipelines with no music must keep rendering without audio."""
    track, err, _ = VideoCompose()._resolve_audio_for_render({}, {"cuts": []}, video)
    assert track is None
    assert err is None


def test_render_via_ffmpeg_end_to_end_is_audible(tmp_path, music):
    """Exercise the real render path, not just the resolver.

    `render_runtime="ffmpeg"` returns early via `_render_via_ffmpeg`, so a
    resolver-only test passes while the actual render still comes out silent.
    That gap is how the original bug survived: `_compose()` reads only
    `audio_path`, and nothing populated it from the edit artifact.
    """
    clip = tmp_path / "clip.mp4"
    out = tmp_path / "out.mp4"
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=6:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
    ])

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "renderer_family": "documentary-montage",
        "cuts": [
            {"id": "cut_01", "source": "asset_a", "in_seconds": 0.0, "out_seconds": 4.0}
        ],
        "audio": {"music": {"asset_id": "asset_music_bed", "volume": 0.7}},
        "metadata": {"silence_window": {"start_seconds": 1.0, "end_seconds": 2.5}},
    }
    manifest = {
        "version": "1.0",
        "assets": [
            {"id": "asset_a", "type": "video", "path": str(clip),
             "source_tool": "test", "scene_id": "s1"},
            {"id": "asset_music_bed", "type": "music", "path": str(music),
             "source_tool": "test", "scene_id": "global"},
        ],
    }

    result = VideoCompose().execute({
        "operation": "render",
        "output_path": str(out),
        "edit_decisions": edit_decisions,
        "asset_manifest": manifest,
    })

    assert result.success, result.error
    assert out.is_file()
    assert _mean_volume(out) > -60.0, "render path produced a silent track"
    # The approved silence window must survive to the rendered file.
    assert _mean_volume(out, start=1.4, dur=0.9) < _mean_volume(out, start=0.2, dur=0.6) - 20.0

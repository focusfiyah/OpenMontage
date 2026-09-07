"""Overlay-layer cuts in video_compose's FFmpeg compose path.

Regression test for a compose-stage dead end that blocked the whole
`avatar-spokesperson` no-avatar path.

An edit whose `cuts` hold a video primary plus a still insert could not be
rendered by either runtime:

* ``render_runtime="remotion"`` routes ``renderer_family="presenter"`` to the
  Remotion ``TalkingHead`` composition, which exists to *build* a talking head
  from stills plus narration segments and cannot take an already-rendered
  talking video as its primary.
* ``render_runtime="ffmpeg"`` refused the still with "Still image ... in cuts.
  Use operation='render' (auto-routes to Remotion)" -- i.e. it redirected to
  the path that was broken above.

Root cause: ``_compose`` ignored ``cuts[].layer`` entirely and treated every
cut as a sequential concat segment, so a still marked ``layer="overlay"`` --
a timed cutaway composited *over* the primary -- was indistinguishable from a
still meant to occupy its own slot in the timeline. The latter genuinely needs
Remotion (Ken Burns, animated scene types); the former is plain FFmpeg work.

These tests run the real FFmpeg path on tiny lavfi fixtures.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.video.video_compose import VideoCompose

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)


def _make_clip(path: Path, w: int = 640, h: int = 360, d: int = 2) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c=teal:s={w}x{h}:d={d}:r=30",
         "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p",
         "-g", "30", "-keyint_min", "30", str(path)],
        capture_output=True, check=True,
    )


def _make_image(path: Path, w: int = 640, h: int = 360) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=red:s={w}x{h}:d=1",
         "-frames:v", "1", str(path)],
        capture_output=True, check=True,
    )


def _duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]
    ).decode().strip()
    return float(out)


def _pixel(path: Path, at: float) -> tuple[int, int, int]:
    """Sample the centre pixel at timestamp ``at`` as (r, g, b)."""
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-ss", str(at), "-i", str(path),
         "-frames:v", "1", "-vf", "crop=2:2:iw/2:ih/2,scale=1:1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    )
    return raw[0], raw[1], raw[2]


def _video_primary_with_still_overlay(clip: Path, image: Path) -> dict:
    return {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "renderer_family": "presenter",
        "cuts": [
            {
                "id": "c1",
                "source": str(clip),
                "in_seconds": 0,
                "out_seconds": 2,
                "layer": "primary",
            },
            {
                "id": "c2",
                "source": str(image),
                "in_seconds": 0.5,
                "out_seconds": 1.0,
                "layer": "overlay",
            },
        ],
    }


def test_compose_accepts_still_overlay_cut_over_video_primary(tmp_path):
    """A still marked layer='overlay' composites instead of being refused."""
    clip = tmp_path / "clip.mp4"
    image = tmp_path / "insert.png"
    _make_clip(clip)
    _make_image(image)
    out = tmp_path / "out.mp4"

    r = VideoCompose().execute({
        "operation": "compose",
        "edit_decisions": _video_primary_with_still_overlay(clip, image),
        "output_path": str(out),
    })

    assert r.success, r.error
    assert out.exists()


def test_still_overlay_cut_does_not_extend_the_timeline(tmp_path):
    """The overlay sits on top of the primary; it does not concat after it."""
    clip = tmp_path / "clip.mp4"
    image = tmp_path / "insert.png"
    _make_clip(clip, d=2)
    _make_image(image)
    out = tmp_path / "out.mp4"

    r = VideoCompose().execute({
        "operation": "compose",
        "edit_decisions": _video_primary_with_still_overlay(clip, image),
        "output_path": str(out),
    })
    assert r.success, r.error

    # Primary is 2s. Concatenating the 0.5s overlay would give ~2.5s.
    assert _duration(out) == pytest.approx(2.0, abs=0.25)


def test_still_overlay_cut_is_visible_only_inside_its_window(tmp_path):
    """The overlay is timed: red inside 0.5-1.0s, teal primary outside it."""
    clip = tmp_path / "clip.mp4"
    image = tmp_path / "insert.png"
    _make_clip(clip, d=2)
    _make_image(image)
    out = tmp_path / "out.mp4"

    r = VideoCompose().execute({
        "operation": "compose",
        "edit_decisions": _video_primary_with_still_overlay(clip, image),
        "output_path": str(out),
    })
    assert r.success, r.error

    inside_r, inside_g, inside_b = _pixel(out, 0.7)
    assert inside_r > 150 and inside_g < 90 and inside_b < 90, (
        f"expected the red overlay at 0.7s, got rgb({inside_r},{inside_g},{inside_b})"
    )

    after_r, after_g, after_b = _pixel(out, 1.6)
    assert after_r < 90 and after_b > 90, (
        f"expected the teal primary at 1.6s, got rgb({after_r},{after_g},{after_b})"
    )


def test_render_operation_composes_video_primary_with_still_insert(tmp_path):
    """The reported repro, end to end through operation='render'.

    This is the shape the avatar-spokesperson no-avatar pivot always produces:
    a generated talking video plus support stills, addressed by asset ID, with
    renderer_family='presenter'. Both runtimes previously refused it -- Remotion
    because TalkingHead cannot take a rendered video as its primary, FFmpeg
    because of the still-in-cuts guard that redirected back to Remotion.
    """
    clip = tmp_path / "presenter.mp4"
    image = tmp_path / "insert.png"
    _make_clip(clip, d=2)
    _make_image(image)
    out = tmp_path / "final.mp4"

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "renderer_family": "presenter",
        "cuts": [
            {"id": "c1", "source": "presenter_take", "in_seconds": 0,
             "out_seconds": 2, "layer": "primary"},
            {"id": "c2", "source": "condition_insert", "in_seconds": 0.5,
             "out_seconds": 1.0, "layer": "overlay"},
        ],
    }
    asset_manifest = {
        "version": "1.0",
        "assets": [
            {"id": "presenter_take", "type": "video", "path": str(clip),
             "source_tool": "kling_video", "scene_id": "sc1"},
            {"id": "condition_insert", "type": "image", "path": str(image),
             "source_tool": "flux_image", "scene_id": "sc2"},
        ],
    }

    r = VideoCompose().execute({
        "operation": "render",
        "edit_decisions": edit_decisions,
        "asset_manifest": asset_manifest,
        "output_path": str(out),
    })

    assert r.success, r.error
    assert out.exists()
    assert _duration(out) == pytest.approx(2.0, abs=0.25)


def test_overlay_cut_honours_scale_and_position(tmp_path):
    """A scaled, anchored overlay leaves the opposite corner untouched."""
    clip = tmp_path / "clip.mp4"
    image = tmp_path / "insert.png"
    _make_clip(clip, w=640, h=360, d=2)
    _make_image(image, w=640, h=360)
    out = tmp_path / "out.mp4"

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [
            {"id": "c1", "source": str(clip), "in_seconds": 0, "out_seconds": 2,
             "layer": "primary"},
            {"id": "c2", "source": str(image), "in_seconds": 0, "out_seconds": 2,
             "layer": "overlay",
             "transform": {"scale": 0.25, "position": "top-left"}},
        ],
        "metadata": {"compose_target": {"width": 640, "height": 360}},
    }

    r = VideoCompose().execute({
        "operation": "compose",
        "edit_decisions": edit_decisions,
        "output_path": str(out),
    })
    assert r.success, r.error

    # A quarter-size overlay anchored top-left must not reach frame centre.
    centre_r, centre_g, centre_b = _pixel(out, 1.0)
    assert centre_r < 90 and centre_b > 90, (
        f"scaled overlay leaked into frame centre: rgb({centre_r},{centre_g},{centre_b})"
    )


def test_compose_still_rejects_a_still_as_a_primary_cut(tmp_path):
    """The existing guardrail is preserved for sequential still cuts.

    A still that occupies its own slot in the timeline still needs Remotion
    (Ken Burns, animated scene types). Only overlay-layer stills are handled
    here, and an omitted `layer` defaults to primary, so pre-existing edits
    behave exactly as before.
    """
    clip = tmp_path / "clip.mp4"
    image = tmp_path / "insert.png"
    _make_clip(clip)
    _make_image(image)
    out = tmp_path / "out.mp4"

    edit_decisions = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [
            {"id": "c1", "source": str(clip), "in_seconds": 0, "out_seconds": 2},
            # No `layer` key at all -> schema default "primary".
            {"id": "c2", "source": str(image), "in_seconds": 0, "out_seconds": 1},
        ],
    }

    r = VideoCompose().execute({
        "operation": "compose",
        "edit_decisions": edit_decisions,
        "output_path": str(out),
    })

    assert not r.success
    assert "Still image" in (r.error or "")

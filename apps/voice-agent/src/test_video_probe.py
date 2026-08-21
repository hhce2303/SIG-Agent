"""Unit tests de `server/video_probe.py` — parser mínimo de `moov/mvhd`, sin archivos de video
reales: se construyen bytes MP4 sintéticos pero estructuralmente válidos (mismo espíritu que
`test_video_streaming.py`, dominio puro con I/O acotado a un archivo temporal).
"""

import struct

from server.video_probe import probe_mp4_duration_seconds


def _box(box_type: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), box_type) + body


def _mvhd_v0(timescale: int, duration: int) -> bytes:
    body = bytes([0, 0, 0, 0]) + b"\x00" * 4 + b"\x00" * 4 + struct.pack(">I", timescale) + struct.pack(">I", duration)
    return _box(b"mvhd", body)


def _mvhd_v1(timescale: int, duration: int) -> bytes:
    body = bytes([1, 0, 0, 0]) + b"\x00" * 8 + b"\x00" * 8 + struct.pack(">I", timescale) + struct.pack(">Q", duration)
    return _box(b"mvhd", body)


def _write_mp4(tmp_path, moov_children: bytes, other_top_level: bytes = b""):
    ftyp = _box(b"ftyp", b"isom" + b"\x00" * 4)
    moov = _box(b"moov", moov_children)
    path = tmp_path / "video.mp4"
    path.write_bytes(ftyp + other_top_level + moov)
    return str(path)


def test_extracts_duration_from_version_0_mvhd(tmp_path):
    path = _write_mp4(tmp_path, _mvhd_v0(timescale=1000, duration=42_000))

    assert probe_mp4_duration_seconds(path) == 42.0


def test_extracts_duration_from_version_1_mvhd(tmp_path):
    path = _write_mp4(tmp_path, _mvhd_v1(timescale=90_000, duration=90_000 * 30))

    assert probe_mp4_duration_seconds(path) == 30.0


def test_skips_sibling_boxes_inside_moov_before_finding_mvhd(tmp_path):
    # `moov` real trae `trak`/`udta`/etc. antes o después de `mvhd` — confirma que el scan de
    # hijos no asume que mvhd es el primer box.
    unrelated = _box(b"udta", b"whatever-metadata")
    path = _write_mp4(tmp_path, unrelated + _mvhd_v0(timescale=1000, duration=5000))

    assert probe_mp4_duration_seconds(path) == 5.0


def test_skips_top_level_boxes_before_moov(tmp_path):
    free_box = _box(b"free", b"\x00" * 20)
    path = _write_mp4(tmp_path, _mvhd_v0(timescale=1000, duration=1000), other_top_level=free_box)

    assert probe_mp4_duration_seconds(path) == 1.0


def test_returns_none_for_a_non_mp4_file(tmp_path):
    path = tmp_path / "not-a-video.txt"
    path.write_bytes(b"this is not a video file at all, just some text bytes")

    assert probe_mp4_duration_seconds(str(path)) is None


def test_returns_none_when_moov_has_no_mvhd(tmp_path):
    path = _write_mp4(tmp_path, _box(b"udta", b"only metadata, no mvhd"))

    assert probe_mp4_duration_seconds(path) is None


def test_returns_none_for_a_missing_file():
    assert probe_mp4_duration_seconds("C:/definitely/does/not/exist.mp4") is None


def test_returns_none_for_zero_timescale(tmp_path):
    # timescale=0 dividiría por cero — se trata como "no se pudo detectar", no como crash.
    path = _write_mp4(tmp_path, _mvhd_v0(timescale=0, duration=1000))

    assert probe_mp4_duration_seconds(path) is None


def test_returns_none_for_a_truncated_box_header(tmp_path):
    path = tmp_path / "truncated.mp4"
    path.write_bytes(_box(b"ftyp", b"isom") + b"\x00\x00\x00")  # header incompleto al final

    assert probe_mp4_duration_seconds(str(path)) is None

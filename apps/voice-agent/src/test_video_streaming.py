"""Unit tests de `server/video_streaming.py` (ADR-0009) — dominio puro sin FastAPI real, más un
test de `iter_file_range` contra un archivo temporal real (única parte con I/O).
"""

from server.video_streaming import iter_file_range, parse_range_header


def test_no_range_header_returns_none():
    assert parse_range_header(None, file_size=1000) is None


def test_simple_range_is_parsed():
    assert parse_range_header("bytes=0-499", file_size=1000) == (0, 499)


def test_open_ended_range_extends_to_the_end_of_the_file():
    assert parse_range_header("bytes=500-", file_size=1000) == (500, 999)


def test_suffix_range_returns_the_last_n_bytes():
    assert parse_range_header("bytes=-100", file_size=1000) == (900, 999)


def test_end_beyond_file_size_is_clamped():
    assert parse_range_header("bytes=0-9999", file_size=1000) == (0, 999)


def test_start_at_or_beyond_file_size_is_rejected():
    assert parse_range_header("bytes=1000-1500", file_size=1000) is None


def test_malformed_range_is_rejected():
    assert parse_range_header("not-a-range", file_size=1000) is None
    assert parse_range_header("bytes=abc-def", file_size=1000) is None


def test_multipart_range_only_uses_the_first_range():
    # Sin soporte de multipart/byteranges (no lo necesita un <video> real) — usa el primero y
    # descarta el resto en vez de fallar.
    assert parse_range_header("bytes=0-99,200-299", file_size=1000) == (0, 99)


def test_iter_file_range_reads_only_the_requested_bytes(tmp_path):
    file_path = tmp_path / "video.bin"
    file_path.write_bytes(bytes(range(256)) * 10)  # 2560 bytes

    chunks = list(iter_file_range(str(file_path), start=10, end=19, chunk_size=4))
    data = b"".join(chunks)

    assert data == (bytes(range(256)) * 10)[10:20]
    assert len(data) == 10

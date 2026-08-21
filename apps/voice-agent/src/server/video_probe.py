"""Duración de un archivo de video MP4/MOV — parser mínimo del box `moov/mvhd` (ISO base media
file format), sin dependencia nueva (nada de ffmpeg/ffprobe/moviepy). Ver ADR-0012 (upload real
de video) — reemplaza pedirle la duración a mano a quien sube el archivo, cuando se puede
detectar; sigue habiendo un fallback manual cuando esto devuelve `None`.

Best-effort a propósito: cualquier archivo que no sea un MP4/MOV bien formado, o cuyo `mvhd` no
aparezca donde este parser sabe buscarlo (ej. MP4 fragmentado con `moov` atípico), devuelve
`None` — nunca levanta una excepción que el caller tenga que manejar como error duro.
"""

import struct

_BOX_HEADER = struct.Struct(">I4s")
_EXTENDED_SIZE = struct.Struct(">Q")


def probe_mp4_duration_seconds(path: str) -> float | None:
    try:
        with open(path, "rb") as handle:
            file_size = _file_size(handle)
            moov_bounds = _find_top_level_box(handle, file_size, b"moov")
            if moov_bounds is None:
                return None
            mvhd_body = _find_child_box(handle, moov_bounds[0], moov_bounds[1], b"mvhd")
            if mvhd_body is None:
                return None
            return _parse_mvhd(mvhd_body)
    except (OSError, struct.error, ValueError):
        return None


def _file_size(handle) -> int:
    handle.seek(0, 2)
    return handle.tell()


def _read_box_header(handle, pos: int, region_end: int) -> tuple[int, bytes, int] | None:
    """Devuelve `(size, type, header_len)` para el box que arranca en `pos`, o `None` si no hay
    un header completo ahí (fin de archivo/región inesperado)."""

    if pos + 8 > region_end:
        return None

    handle.seek(pos)
    header = handle.read(8)
    if len(header) < 8:
        return None

    size, box_type = _BOX_HEADER.unpack(header)
    header_len = 8

    if size == 1:  # tamaño de 64 bits en los siguientes 8 bytes
        extended = handle.read(8)
        if len(extended) < 8:
            return None
        size = _EXTENDED_SIZE.unpack(extended)[0]
        header_len = 16
    elif size == 0:  # el box se extiende hasta el final de la región (raro, pero legal)
        size = region_end - pos

    if size < header_len:
        return None

    return size, box_type, header_len


def _find_top_level_box(handle, file_size: int, target: bytes) -> tuple[int, int] | None:
    pos = 0
    while pos < file_size:
        parsed = _read_box_header(handle, pos, file_size)
        if parsed is None:
            return None
        size, box_type, header_len = parsed
        if box_type == target:
            return pos + header_len, pos + size
        pos += size
    return None


def _find_child_box(handle, start: int, end: int, target: bytes) -> bytes | None:
    pos = start
    while pos < end:
        parsed = _read_box_header(handle, pos, end)
        if parsed is None:
            return None
        size, box_type, header_len = parsed
        if box_type == target:
            handle.seek(pos + header_len)
            return handle.read(size - header_len)
        pos += size
    return None


def _parse_mvhd(body: bytes) -> float | None:
    if len(body) < 4:
        return None

    version = body[0]
    if version == 1:
        if len(body) < 32:
            return None
        timescale = struct.unpack(">I", body[20:24])[0]
        duration = struct.unpack(">Q", body[24:32])[0]
    else:
        if len(body) < 20:
            return None
        timescale = struct.unpack(">I", body[12:16])[0]
        duration = struct.unpack(">I", body[16:20])[0]

    if timescale == 0:
        return None
    return duration / timescale

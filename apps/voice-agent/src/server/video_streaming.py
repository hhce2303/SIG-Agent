"""Streaming de archivos de video con soporte de HTTP Range — ver ADR-0009.

Dominio pequeño y puro a propósito: `parse_range_header` no toca el filesystem ni FastAPI, así
que se puede testear sin un servidor real (mismo espíritu que `core/scoring.py`). `iter_file_range`
es el único bit con I/O, y es deliberadamente simple (abrir, seek, leer en chunks) — sin
dependencia nueva, la librería estándar alcanza para esto.
"""

from collections.abc import Iterator

CHUNK_SIZE = 1024 * 1024  # 1 MiB


def parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    """Devuelve `(start, end)` (inclusive, 0-indexed) para un header `Range: bytes=start-end`.

    `None` si no hay header (el caller debe servir el archivo completo) o si el rango es
    inválido/no satisfacible (start >= file_size, o start > end) — el caller responde 416 en
    ese caso, nunca deja pasar un rango sin sentido al lector de archivo.
    """

    if not range_header:
        return None

    if not range_header.startswith("bytes="):
        return None

    range_spec = range_header[len("bytes="):].split(",")[0].strip()  # un solo rango, no multipart
    if "-" not in range_spec:
        return None

    start_str, _, end_str = range_spec.partition("-")

    try:
        if start_str == "":
            # "bytes=-500" -> los últimos 500 bytes.
            suffix_length = int(end_str)
            if suffix_length <= 0:
                return None
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str != "" else file_size - 1
    except ValueError:
        return None

    end = min(end, file_size - 1)

    if start < 0 or start > end or start >= file_size:
        return None

    return start, end


def iter_file_range(path: str, start: int, end: int, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    """Generador que produce los bytes `[start, end]` (inclusive) de `path`, en chunks — nunca
    carga el archivo completo en memoria del servidor.
    """

    remaining = end - start + 1

    with open(path, "rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk

"""Unit tests de `core.paths` — `base_dir()`/`bundle_dir()` bajo `sys.frozen`/`sys._MEIPASS`
simulados (docs/designs/empaquetado-ejecutable-backend.md, Premisas 4 y 6).

Baratos y corren en CI sin necesitar un build real de PyInstaller — la Premisa 4 del design doc
señala esto explícitamente como la cobertura que faltaba antes de este test: el único chequeo de
anclaje de rutas del plan original era el smoke test manual en una máquina Windows limpia.
"""

import os
import sys

import core.paths as paths


def test_base_dir_resolves_to_src_root_when_not_frozen():
    # apps/voice-agent/src/core/paths.py -> apps/voice-agent/src/
    expected = os.path.dirname(os.path.dirname(os.path.abspath(paths.__file__)))

    assert paths.base_dir() == expected


def test_bundle_dir_resolves_to_src_root_when_not_frozen_and_no_meipass():
    expected = os.path.dirname(os.path.dirname(os.path.abspath(paths.__file__)))

    assert paths.bundle_dir() == expected


def test_base_dir_resolves_to_executable_dir_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join("C:", "dist", "server_main", "server_main.exe"))

    assert paths.base_dir() == os.path.join("C:", "dist", "server_main")


def test_bundle_dir_resolves_to_meipass_when_set_regardless_of_frozen(monkeypatch):
    # sys._MEIPASS es lo que PyInstaller setea en runtime -- ese es el chequeo real, no
    # sys.frozen (que solo afecta a base_dir()).
    monkeypatch.setattr(sys, "_MEIPASS", os.path.join("C:", "dist", "server_main", "_internal"), raising=False)

    assert paths.bundle_dir() == os.path.join("C:", "dist", "server_main", "_internal")


def test_base_dir_and_bundle_dir_differ_under_onedir_layout(monkeypatch):
    """El hallazgo crítico de la revisión de ingeniería: bajo `--onedir`, `base_dir()`
    (directorio del `.exe`) y `bundle_dir()` (`_internal/`, donde vive `datas=[]`) son rutas
    DISTINTAS -- confundirlas fue el bug real que este test existe para prevenir que reaparezca."""
    exe_dir = os.path.join("C:", "dist", "server_main")
    internal_dir = os.path.join(exe_dir, "_internal")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join(exe_dir, "server_main.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", internal_dir, raising=False)

    assert paths.base_dir() == exe_dir
    assert paths.bundle_dir() == internal_dir
    assert paths.base_dir() != paths.bundle_dir()

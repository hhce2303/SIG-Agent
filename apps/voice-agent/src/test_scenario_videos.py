"""Unit tests de `SQLiteScenarioVideoStore` (docs/designs/escenarios-de-video.md, ADR-0009/
ADR-0010) — mismo patrón que `test_scenarios.py`: SQLite real contra un archivo temporal.
"""

from core.ports import ScenarioVideo, VideoGroundTruthPoint
from persistence.sqlite_scenario_video_store import SQLiteScenarioVideoStore


def _video(scenario_id: str = "robbery_001", **overrides) -> ScenarioVideo:
    defaults = dict(
        scenario_id=scenario_id,
        video_path="C:/videos/robbery_001.mp4",
        video_checksum="abc123",
        duration_seconds=42.0,
        content_type="video/mp4",
        ground_truth_points=[
            VideoGroundTruthPoint(
                key="suspect_description",
                label="Suspect description",
                match_hints=["red jacket", "hoodie"],
                visible_from_seconds=2.0,
                visible_to_seconds=10.0,
            ),
        ],
    )
    defaults.update(overrides)
    return ScenarioVideo(**defaults)


def test_get_returns_none_when_the_scenario_has_no_video(tmp_path):
    store = SQLiteScenarioVideoStore(str(tmp_path / "videos.db"))

    assert store.get("does-not-exist") is None


def test_upsert_then_get_round_trips_ground_truth_points(tmp_path):
    store = SQLiteScenarioVideoStore(str(tmp_path / "videos.db"))
    video = _video()

    store.upsert(video)
    fetched = store.get("robbery_001")

    assert fetched.video_path == "C:/videos/robbery_001.mp4"
    assert fetched.video_checksum == "abc123"
    assert fetched.duration_seconds == 42.0
    assert fetched.ground_truth_points == [
        VideoGroundTruthPoint(
            key="suspect_description",
            label="Suspect description",
            match_hints=["red jacket", "hoodie"],
            visible_from_seconds=2.0,
            visible_to_seconds=10.0,
        ),
    ]
    assert fetched.created_at > 0
    assert fetched.updated_at > 0


def test_upsert_is_a_true_upsert_not_a_duplicate_row(tmp_path):
    # PK = scenario_id (relación 1:1) — un segundo upsert reemplaza, no agrega una fila más.
    store = SQLiteScenarioVideoStore(str(tmp_path / "videos.db"))
    store.upsert(_video())

    store.upsert(_video(video_path="C:/videos/robbery_001_v2.mp4", video_checksum="def456"))

    fetched = store.get("robbery_001")
    assert fetched.video_path == "C:/videos/robbery_001_v2.mp4"
    assert fetched.video_checksum == "def456"


def test_delete_removes_the_reference(tmp_path):
    store = SQLiteScenarioVideoStore(str(tmp_path / "videos.db"))
    store.upsert(_video())

    store.delete("robbery_001")

    assert store.get("robbery_001") is None


def test_two_scenarios_can_each_have_their_own_video(tmp_path):
    store = SQLiteScenarioVideoStore(str(tmp_path / "videos.db"))
    store.upsert(_video(scenario_id="robbery_001"))
    store.upsert(_video(scenario_id="robbery_002", video_path="C:/videos/robbery_002.mp4"))

    assert store.get("robbery_001").video_path == "C:/videos/robbery_001.mp4"
    assert store.get("robbery_002").video_path == "C:/videos/robbery_002.mp4"

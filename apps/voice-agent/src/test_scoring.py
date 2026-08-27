"""Unit tests del motor de métricas/ponderado (roadmap Fase 2, TODO-10 resuelto).

Dominio puro — sin FastAPI, sin SQLite, sin reloj real (todos los timestamps son literales
inyectados, igual que en `test_turn_state.py`).
"""

from core.ports import CriticalDataPoint, ScenarioLocation, VideoGroundTruthPoint
from core.scoring import ScoreWeights, is_location_configured, score_session
from core.turn_state import TurnState, TurnTransition

VEHICLE_THEFT_POINTS = [
    CriticalDataPoint(key="incident_description", label="What happened"),
    CriticalDataPoint(key="vehicle_description", label="Vehicle description"),
    CriticalDataPoint(key="license_plate", label="License plate"),
    CriticalDataPoint(key="last_location", label="Last known location"),
]


def _operator(text: str, at: float) -> dict:
    return {"role": "operator", "text": text, "at": at}


def test_network_drop_outcome_returns_no_evaluation_regardless_of_content():
    transcript = [_operator("My car was stolen, license plate ABC123.", at=1010.0)]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1100.0, outcome="network_drop")

    assert result is None


def test_ended_outcome_scores_even_with_an_empty_transcript():
    result = score_session([], VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1010.0, outcome="ended")

    assert result is not None
    assert result["category_scores"]["completeness"] == 0
    assert result["missing"] == [point.label for point in VEHICLE_THEFT_POINTS]


def test_full_completeness_and_quick_response_score_near_the_top():
    transcript = [_operator(
        "Here's what happened: a vehicle was stolen, a white Toyota Camry, license plate "
        "ABC123, last seen near the shopping center.",
        at=1010.0,  # 10s después de empezar, bien dentro del target de 60s
    )]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["completeness"] == 100
    assert result["category_scores"]["time_to_critical_data"] == 100
    assert result["missing"] == []
    assert result["overall_score"] > 80


def test_missing_points_are_listed_and_lower_completeness():
    # A propósito sin las palabras "vehicle"/"description"/"what"/"happened"/"location" — el
    # matching es por palabra clave (ver docstring del módulo), así que el texto de prueba debe
    # evitar coincidencias accidentales para que el resultado sea significativo.
    transcript = [_operator("A car was taken, license plate ABC123.", at=1010.0)]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert "License plate" in result["collected"]
    assert "Vehicle description" in result["missing"]
    assert "Last known location" in result["missing"]
    assert 0 < result["category_scores"]["completeness"] < 100


def test_no_critical_data_never_mentioned_scores_zero_time_to_critical():
    transcript = [_operator("I don't have anything else to add right now.", at=1010.0)]

    result = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["time_to_critical_data"] == 0


def test_scenario_without_critical_data_points_does_not_penalize_completeness_or_time():
    result = score_session([_operator("Hello", at=1005.0)], [], started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["completeness"] == 100
    assert result["category_scores"]["time_to_critical_data"] == 100


def test_filler_words_lower_the_clarity_score():
    clean = [_operator("The vehicle was a white sedan parked near the mall.", at=1010.0)]
    fillers = [_operator("Um, so, like, the vehicle was, uh, a white sedan, you know, near the mall.", at=1010.0)]

    clean_result = score_session(clean, [], started_at=1000.0, ended_at=1090.0, outcome="ended")
    fillers_result = score_session(fillers, [], started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert fillers_result["category_scores"]["clarity"] < clean_result["category_scores"]["clarity"]


def test_custom_weights_change_the_composite_score():
    transcript = [_operator("License plate ABC123.", at=1010.0)]

    default = score_session(transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended")
    completeness_only = score_session(
        transcript,
        VEHICLE_THEFT_POINTS,
        started_at=1000.0,
        ended_at=1090.0,
        outcome="ended",
        weights=ScoreWeights(completeness=1.0, time_to_critical_data=0.0, clarity=0.0, total_time=0.0),
    )

    assert default["overall_score"] != completeness_only["overall_score"]
    # Solo 1/4 de los datos críticos mencionados -> con completitud=100% del peso, ~25.
    assert completeness_only["overall_score"] == 25


def test_natural_language_report_without_label_wording_still_scores_low_todo_17():
    # Documenta el bug de TODO-17 tal como se midió en producción: sin `match_hints`, un reporte
    # perfecto en lenguaje natural falla porque nunca repite las palabras del `label` de UI.
    points_without_hints = [
        CriticalDataPoint(key="incident_description", label="What happened"),
        CriticalDataPoint(key="vehicle_description", label="Vehicle description"),
        CriticalDataPoint(key="last_location", label="Last known location"),
        CriticalDataPoint(key="approx_time", label="Approximate time"),
    ]
    transcript = [_operator(
        "There is a white 2021 Toyota Camry stolen from a shopping center parking lot about "
        "two hours ago.",
        at=1010.0,
    )]

    result = score_session(transcript, points_without_hints, started_at=1000.0, ended_at=1090.0, outcome="ended")

    # "last" (de "Last known location") aparece por casualidad en textos distintos, pero ninguno
    # de los otros 3 puntos matchea sin hints — reproduce la falla real, no un caso inventado.
    assert result["category_scores"]["completeness"] < 50


def test_match_hints_fix_scores_the_same_natural_language_report_correctly():
    # Mismo transcript exacto que el test anterior, misma llamada real que documenta TODO-17 —
    # la única diferencia es que el escenario ahora tiene `match_hints` autorados por el creador
    # del escenario. Este es el criterio de aceptación del fix de TODO-17.
    points_with_hints = [
        CriticalDataPoint(
            key="incident_description", label="What happened", match_hints=["stolen", "theft"]
        ),
        CriticalDataPoint(
            key="vehicle_description",
            label="Vehicle description",
            match_hints=["toyota", "camry"],
        ),
        CriticalDataPoint(
            key="last_location",
            label="Last known location",
            match_hints=["shopping center", "parking lot"],
        ),
        CriticalDataPoint(
            key="approx_time", label="Approximate time", match_hints=["hours ago"]
        ),
    ]
    transcript = [_operator(
        "There is a white 2021 Toyota Camry stolen from a shopping center parking lot about "
        "two hours ago.",
        at=1010.0,
    )]

    result = score_session(transcript, points_with_hints, started_at=1000.0, ended_at=1090.0, outcome="ended")

    assert result["category_scores"]["completeness"] == 100
    assert result["missing"] == []


def test_short_match_hint_works_even_though_the_label_never_appears_in_speech():
    # El label ("Vehicle Identification Number") no aparece nunca en el transcript, y el
    # fallback de palabras del label tampoco matchearía nada por sí solo. El hint "vin" (3
    # caracteres) sí matchea porque los hints no llevan el filtro `len(word) > 3` que aplica al
    # fallback de palabras sueltas del label — son frases elegidas a propósito, no un label
    # genérico que necesite ese filtro anti-ruido.
    point = CriticalDataPoint(
        key="vin", label="Vehicle Identification Number", match_hints=["vin"]
    )

    result = score_session(
        [_operator("It's a 2021 Camry, VIN 1HGCM82633A004352.", at=1010.0)],
        [point],
        started_at=1000.0,
        ended_at=1090.0,
        outcome="ended",
    )

    assert result["category_scores"]["completeness"] == 100


def test_video_ground_truth_folds_into_the_same_collected_missing_arrays():
    # ADR-0010/hallazgo de diseño: cobertura de video se pliega en collected/missing, no un
    # panel/categoría paralela — no hay claves nuevas de "video_collected"/"video_missing".
    ground_truth = [
        VideoGroundTruthPoint(
            key="suspect_clothing",
            label="What the suspect was wearing",
            match_hints=["red jacket", "hoodie"],
            visible_from_seconds=2.0,
            visible_to_seconds=8.0,
        ),
        VideoGroundTruthPoint(
            key="getaway_vehicle",
            label="Getaway vehicle",
            match_hints=["black suv", "suv"],
            visible_from_seconds=10.0,
            visible_to_seconds=15.0,
        ),
    ]
    transcript = [_operator("The suspect was wearing a red jacket and fled in a black SUV.", at=1010.0)]

    result = score_session(
        transcript,
        critical_data_points=[],
        started_at=1000.0,
        ended_at=1090.0,
        outcome="ended",
        video_ground_truth=ground_truth,
    )

    assert result["category_scores"]["completeness"] == 100
    assert result["missing"] == []
    assert "video_collected" not in result
    assert "video_missing" not in result


def test_video_reaction_seconds_is_none_without_a_video_scenario():
    result = score_session(
        [_operator("License plate ABC123.", at=1010.0)],
        VEHICLE_THEFT_POINTS,
        started_at=1000.0,
        ended_at=1090.0,
        outcome="ended",
    )

    assert result["video_reaction_seconds"] is None


def test_video_reaction_seconds_measured_from_video_ended_at_not_call_started_at():
    # El entrenando vio el video, se tomó un café, y arrancó la llamada 10 minutos después
    # (started_at muy lejos de video_ended_at) — la reacción real es rápida (5s) una vez que
    # habló, y debe medirse desde que terminó el video, no desde el inicio de la llamada.
    ground_truth = [
        VideoGroundTruthPoint(key="weapon", label="Weapon involved", match_hints=["knife"]),
    ]
    video_ended_at = 1000.0
    call_started_at = 1600.0  # 10 minutos después de que terminó el video
    transcript = [_operator("The suspect had a knife.", at=call_started_at + 5.0)]

    result = score_session(
        transcript,
        critical_data_points=[],
        started_at=call_started_at,
        ended_at=call_started_at + 90.0,
        outcome="ended",
        video_ground_truth=ground_truth,
        video_ended_at=video_ended_at,
    )

    # Si esto se midiera (incorrectamente) desde started_at, sería 5.0 igual por casualidad de
    # este fixture — la aserción real que importa es contra video_ended_at explícitamente.
    assert result["video_reaction_seconds"] == call_started_at + 5.0 - video_ended_at


def test_video_reaction_seconds_is_none_when_ground_truth_is_never_mentioned():
    ground_truth = [VideoGroundTruthPoint(key="weapon", label="Weapon", match_hints=["knife"])]

    result = score_session(
        [_operator("I don't remember anything else.", at=1010.0)],
        critical_data_points=[],
        started_at=1000.0,
        ended_at=1090.0,
        outcome="ended",
        video_ground_truth=ground_truth,
        video_ended_at=990.0,
    )

    assert result["video_reaction_seconds"] is None


def test_score_weights_from_env_override_defaults(monkeypatch):
    monkeypatch.setenv("METRICS_WEIGHT_COMPLETENESS", "1")
    monkeypatch.setenv("METRICS_WEIGHT_TIME_TO_CRITICAL", "0")
    monkeypatch.setenv("METRICS_WEIGHT_CLARITY", "0")
    monkeypatch.setenv("METRICS_WEIGHT_TOTAL_TIME", "0")

    weights = ScoreWeights.from_env()

    assert weights == ScoreWeights(completeness=1.0, time_to_critical_data=0.0, clarity=0.0, total_time=0.0)


# --- communication_coaching (T1, docs/designs/motor-de-metricas.md) -----------------------------
# Panel nuevo, separado de `category_scores` (fórmula ponderada ya cerrada, TODO-10) — ver Fase 2
# Pass 1 de la revisión. `category_scores`/`overall_score` NUNCA cambian con estos tests.


def test_communication_coaching_present_but_empty_without_turn_history():
    result = score_session([], VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1010.0, outcome="ended")

    assert result["communication_coaching"] == {
        "response_latency": None,
        "transcription_confidence": None,
        "coherence": None,
        "english_quality": None,
    }


def test_communication_coaching_response_latency_computed_from_turn_history():
    history = [
        TurnTransition(TurnState.DISPATCHER_SPEAKING, TurnState.LISTENING, "dispatcher_finished_speaking", at=1005.0),
        TurnTransition(TurnState.LISTENING, TurnState.SUPERVISOR_SPEAKING, "supervisor_started_speaking", at=1007.0),
    ]

    result = score_session(
        [], VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1010.0, outcome="ended", turn_history=history
    )

    latency = result["communication_coaching"]["response_latency"]
    assert latency["average_ms"] == 2000
    assert latency["rating"] == "good"
    # category_scores/overall_score no se tocan por agregar turn_history — contrato cerrado. Se
    # compara contra una llamada idéntica sin turn_history: debe dar exactamente el mismo dict.
    baseline = score_session([], VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1010.0, outcome="ended")
    assert result["category_scores"] == baseline["category_scores"]
    assert result["overall_score"] == baseline["overall_score"]


def test_communication_coaching_judge_fields_stay_none_until_finish_call_fills_them():
    # score_session es puro (ADR-0006) — nunca llama al judge. `coherence`/`english_quality`/
    # `transcription_confidence` los completa `finish_call` (server/app.py) después, con el
    # resultado del adaptador async (`llm/metrics_judge.py`).
    result = score_session([], VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1010.0, outcome="ended")

    coaching = result["communication_coaching"]
    assert coaching["transcription_confidence"] is None
    assert coaching["coherence"] is None
    assert coaching["english_quality"] is None


# ---------------------------------------------------------------------------
# Ubicación del incidente — docs/designs/ubicacion-del-incidente.md (autoplan 2026-08-21/22).
# ---------------------------------------------------------------------------


def test_is_location_configured_false_for_none():
    assert is_location_configured(None) is False


def test_is_location_configured_false_when_all_text_fields_are_empty():
    location = ScenarioLocation(scenario_id="s1", marker_x=0.5, marker_y=0.5)

    assert is_location_configured(location) is False


def test_is_location_configured_true_with_just_one_field():
    location = ScenarioLocation(scenario_id="s1", street="5th Avenue")

    assert is_location_configured(location) is True


def test_no_location_configured_produces_identical_evaluation_to_before_this_feature():
    # Regresión mandatoria (Fase 3 Sección 3 del design doc) — cualquier sesión sin ubicación
    # configurada debe puntuar exactamente igual que antes de este feature.
    kwargs = dict(started_at=1000.0, ended_at=1090.0, outcome="ended")
    transcript = [_operator("A white Toyota Camry, license plate ABC123, near the shopping center.", at=1010.0)]

    with_none = score_session(transcript, VEHICLE_THEFT_POINTS, location=None, **kwargs)
    without_param = score_session(transcript, VEHICLE_THEFT_POINTS, **kwargs)

    assert with_none == without_param


def test_location_facts_mentioned_are_collected_not_missing_todo17_regression():
    # TODO-17 (docs/architecture/TODOS.md): un reporte real y correcto en lenguaje natural puntuó
    # 17/100 porque el matching era contra el label, no contra contenido real. Esta es la misma
    # clase de regresión para ubicación: un trainee que SÍ recibió la calle configurada (vía la
    # nueva pantalla de pre-llamada) y la repite debe puntuar collected, no missing.
    location = ScenarioLocation(scenario_id="s1", street="5th Avenue", cross_street="Main Street")
    transcript = [_operator("The incident happened on 5th Avenue, near Main Street.", at=1010.0)]

    result = score_session(transcript, [], started_at=1000.0, ended_at=1090.0, outcome="ended", location=location)

    assert any(item.startswith("Street:") for item in result["collected"])
    assert any(item.startswith("Cross street:") for item in result["collected"])
    assert result["missing"] == []


def test_location_word_fallback_disabled_generic_word_does_not_falsely_match():
    # Hallazgo crítico A3 (voz independiente de ingeniería, Fase 3): usar el valor real como label
    # ("Street: 5th Avenue") activaría el fallback de palabra suelta de `_matches_point` en
    # cualquier transcript que contenga "avenue" — `word_fallback=False` lo desactiva.
    location = ScenarioLocation(scenario_id="s1", street="5th Avenue")
    # Menciona "avenue" en un contexto que NO es la ubicación real, y nunca dice "5th avenue".
    transcript = [_operator("I was walking down the avenue when I noticed something odd.", at=1010.0)]

    result = score_session(transcript, [], started_at=1000.0, ended_at=1090.0, outcome="ended", location=location)

    assert result["collected"] == []
    assert any(item.startswith("Street:") for item in result["missing"])


def test_location_points_never_advance_time_to_critical_data():
    # Hallazgo B5 — cualquier punto en all_points solo puede adelantar/igualar
    # time_to_critical_data (30% del peso). counts_toward_timing=False excluye los puntos de
    # ubicación de ese cálculo: mencionarla temprano no debe, por sí sola, subir esa categoría.
    location = ScenarioLocation(scenario_id="s1", street="5th Avenue")
    # El transcript menciona la calle muy pronto (elapsed=1s) pero NINGÚN otro dato crítico.
    transcript = [_operator("It happened on 5th Avenue.", at=1001.0)]

    with_location = score_session(
        transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended", location=location
    )
    without_location = score_session(
        transcript, VEHICLE_THEFT_POINTS, started_at=1000.0, ended_at=1090.0, outcome="ended"
    )

    assert with_location["category_scores"]["time_to_critical_data"] == without_location["category_scores"]["time_to_critical_data"]
    # Pero SÍ cuenta para completeness — las dos categorías se afectan de forma independiente.
    assert with_location["category_scores"]["completeness"] > without_location["category_scores"]["completeness"]


def test_location_with_marker_only_and_no_text_produces_no_scoring_points():
    # B10 — un marcador sin ningún campo de texto no debe generar puntos que siempre fallan.
    location = ScenarioLocation(scenario_id="s1", marker_x=0.5, marker_y=0.5)

    result = score_session([], [], started_at=1000.0, ended_at=1090.0, outcome="ended", location=location)

    assert result["collected"] == []
    assert result["missing"] == []
    assert result["category_scores"]["completeness"] == 100  # sin puntos = no penaliza (mismo que hoy)

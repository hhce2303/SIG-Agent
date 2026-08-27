"""Migración one-shot: pre-llena `ScenarioLocation` para los 3 escenarios semilla y retira el
`CriticalDataPoint` ad-hoc de ubicación que cada uno ya tenía — docs/designs/ubicacion-del-incidente.md,
Fase 3 Sección 2 punto 6 / Fase 1 0A punto 6.

Por qué un script y no simplemente editar `_seed_scenarios()`: `SQLiteScenarioStore.__init__` solo
siembra si la tabla está vacía (`if not self.list()`) — en cualquier base ya poblada (Gate 0,
TODO-20), editar la función semilla no cambia nada. Este script opera directamente sobre las filas
ya existentes.

Retira el punto ad-hoc EN EL MISMO PASO que agrega el `ScenarioLocation` — nunca deja un estado
intermedio con las dos cosas presentes a la vez (contaría el mismo hecho dos veces, ver hallazgo
H2/M1 de la revisión de ingeniería).

Los valores de `street`/`cross_street`/`landmark` que este script escribe son un BORRADOR, no una
verdad final — derivados lo mejor posible de los `match_hints` ya existentes, que son categorías
genéricas ("shopping center", "busy intersection"), no direcciones reales. El supervisor debe
revisar y completar cada uno en el editor de escenarios antes de considerar la migración terminada
(ver "Qué revisar" al final de este archivo).

Uso:
    python migrate_seed_locations.py [--db-path sessions.db] [--dry-run]
"""

import argparse
import sys
import time

from core.ports import ScenarioLocation
from persistence.sqlite_scenario_location_store import SQLiteScenarioLocationStore
from persistence.sqlite_scenario_store import SQLiteScenarioStore

# scenario_id -> (key del CriticalDataPoint ad-hoc a retirar, ScenarioLocation en borrador)
_MIGRATIONS: dict[str, tuple[str, dict]] = {
    "vehicle_theft": (
        "last_location",
        {
            "landmark": "Shopping center parking lot",
            "additional_directions": "Vehicle was parked near the shopping center — confirm exact "
            "street/cross street with the supervisor before relying on this for dispatch.",
        },
    ),
    "domestic_dispute": (
        "address",
        {
            # "next door" (el hint original) no da ninguna dirección real — se deja el borrador
            # deliberadamente vacío de calle/cruce; el supervisor debe completarlo a mano.
            "additional_directions": "Original scenario only said \"next door\" — no real address "
            "was ever defined. Needs a real street/cross street before this scenario's location "
            "scoring is meaningful.",
        },
    ),
    "traffic_accident": (
        "location",
        {
            "landmark": "Busy intersection",
            "additional_directions": "Original scenario described a generic \"busy intersection\" — "
            "confirm a real street/cross street with the supervisor before relying on this for "
            "dispatch.",
        },
    ),
}


def migrate(db_path: str, dry_run: bool = False) -> list[str]:
    """Devuelve la lista de scenario_ids migrados (o que se migrarían, si dry_run=True)."""

    scenario_store = SQLiteScenarioStore(db_path)
    location_store = SQLiteScenarioLocationStore(db_path)
    now = time.time()

    migrated = []
    for scenario_id, (old_key, location_fields) in _MIGRATIONS.items():
        scenario = scenario_store.get(scenario_id)
        if scenario is None:
            continue  # este escenario semilla no existe en esta base — no hay nada que migrar

        has_old_point = any(p.key == old_key for p in scenario.critical_data_points)
        already_has_location = location_store.get(scenario_id) is not None
        if not has_old_point and already_has_location:
            continue  # ya migrado en una corrida anterior — idempotente, no hacer nada de nuevo

        if dry_run:
            migrated.append(scenario_id)
            continue

        # 1. Retirar el punto ad-hoc (si sigue presente).
        if has_old_point:
            scenario.critical_data_points = [
                p for p in scenario.critical_data_points if p.key != old_key
            ]
            scenario_store.update(scenario)

        # 2. Agregar el borrador de ScenarioLocation (solo si no existe ya uno).
        if not already_has_location:
            location_store.upsert(ScenarioLocation(scenario_id=scenario_id, created_at=now, **location_fields))

        migrated.append(scenario_id)

    return migrated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="sessions.db")
    parser.add_argument("--dry-run", action="store_true", help="list what would change, write nothing")
    args = parser.parse_args()

    migrated = migrate(args.db_path, dry_run=args.dry_run)

    verb = "Would migrate" if args.dry_run else "Migrated"
    if not migrated:
        print("Nothing to migrate — either the seed scenarios aren't in this DB, or this already ran.")
    for scenario_id in migrated:
        print(f"{verb}: {scenario_id}")

    if migrated and not args.dry_run:
        print(
            "\nReview each migrated scenario in the editor — the street/cross street/landmark "
            "fields above are drafts derived from the old generic match_hints, not real addresses. "
            "Complete them before relying on location scoring for these scenarios."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())

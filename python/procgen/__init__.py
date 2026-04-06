"""
procgen/__init__.py  — full sphere pipeline entry point
"""
from __future__ import annotations
import logging
from typing import Any

from palimpsest.python.procgen.sphere       import build_sphere, cell_vertices_sorted
from palimpsest.python.procgen.tectonics    import TectonicConfig, run_simulation
from palimpsest.python.procgen.climate      import apply_climate
from palimpsest.python.procgen.resources    import place_resources
from palimpsest.python.procgen.institutions import generate_starting_institutions

log = logging.getLogger(__name__)


def generate_world(num_cells=1000, num_civs=6, seed=0, tectonic_config=None):
    log.info("=== Generating world: %d cells, %d civs, seed=%d ===", num_cells, num_civs, seed)
    sphere   = build_sphere(num_cells, seed=seed)
    tectonic = run_simulation(sphere, config=tectonic_config, seed=seed)
    climate  = apply_climate(sphere, tectonic)
    cells = []
    for i in range(sphere.num_cells):
        verts = cell_vertices_sorted(sphere, i)
        cells.append({
            "id": i, "center": sphere.centers[i].tolist(),
            "vertices": verts, "neighbors": sphere.adjacency[i],
            "terrain": int(climate.terrain[i]), "height": float(tectonic.heights[i]),
            "plate_id": int(tectonic.plate_ids[i]), "is_oceanic": bool(tectonic.is_oceanic[i]),
            "temperature": float(climate.temperature[i]), "moisture": float(climate.moisture[i]),
            "resource_natural": "", "resource_strategic": "", "resource_luxury": "",
        })
    place_resources(cells, seed=seed)
    inst_data = generate_starting_institutions(cells, num_civs=num_civs, seed=seed)
    return {
        "sphere_radius": sphere.sphere_radius, "num_cells": sphere.num_cells,
        "sea_level": tectonic.sea_level, "seed": seed,
        "cells": cells, "civs": inst_data["civs"],
    }

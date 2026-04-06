"""
procgen/climate.py
~~~~~~~~~~~~~~~~~~
Derives temperature, moisture, and terrain classification from
the tectonic height field and spherical geometry.

Temperature:  driven by latitude (equator hot, poles cold) and altitude
Moisture:     driven by latitude bands (ITCZ, horse latitudes, westerlies),
              orographic effect (windward wet, leeward dry),
              and ocean proximity

Both map onto the 19 GDD terrain types (matching WorldSphere.gd enum).
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from palimpsest.python.procgen.sphere     import SphereData
from palimpsest.python.procgen.tectonics  import TectonicResult

log = logging.getLogger(__name__)


# ── Terrain codes (must match WorldSphere.gd enum) ───────────────────────────

DEEP_OCEAN          = 0
OCEAN               = 1
COASTAL             = 2
POLAR_ICE           = 3
TUNDRA              = 4
TAIGA               = 5
TEMPERATE           = 6
GRASSLAND           = 7
SAVANNA             = 8
MEDITERRANEAN       = 9
MONSOON             = 10
TROPICAL            = 11
DESERT              = 12
ARID_DESERT         = 13
XERIC               = 14
DRY_STEPPE          = 15
MONTANE             = 16
MONTANE_IMPASSABLE  = 17
WASTELANDS          = 18


# ── Climate derivation ────────────────────────────────────────────────────────

def compute_temperature(centers: np.ndarray, heights: np.ndarray) -> np.ndarray:
    """
    Temperature ∈ [0, 1]:  0 = polar cold,  1 = equatorial hot.
    Driven by:
      - latitude (|z| component of unit-sphere center)
      - altitude cooling above sea level
    """
    latitude    = np.abs(centers[:, 2])              # 0 = equator, 1 = pole
    base_temp   = 1.0 - latitude                     # warm equator, cold poles

    # Altitude cooling: land cells lose ~0.4 temperature units at max height
    altitude_penalty = np.clip(heights, 0, 1) * 0.4
    temperature      = base_temp - altitude_penalty

    return np.clip(temperature, 0.0, 1.0)


def compute_moisture(
    centers:   np.ndarray,
    heights:   np.ndarray,
    adjacency: dict[int, list[int]],
    is_oceanic: np.ndarray,
    sea_level: float,
) -> np.ndarray:
    """
    Moisture ∈ [0, 1]:  0 = arid,  1 = saturated.

    Sources:
      a) Latitude bands — ITCZ (0°) and sub-polar fronts (60°) are wet;
         horse latitudes (~30°) and poles are dry.
      b) Ocean proximity — cells near ocean get moisture bonus.
      c) Orographic — windward (westerly) slopes are wet; leeward are dry.
    """
    latitude = np.abs(centers[:, 2])   # [0, 1]

    # ── a) Latitude bands ─────────────────────────────────────────────────────
    # ITCZ: peak at latitude 0 → high moisture
    # Horse latitudes: peak at 0.5 (≈ 30°) → dry
    # Sub-polar convergence: peak at 0.8 (≈ 60°) → moderate moisture
    # Polar: dry

    itcz       = np.exp(-((latitude - 0.00) ** 2) / (2 * 0.10 ** 2))
    horse_dry  = np.exp(-((latitude - 0.50) ** 2) / (2 * 0.12 ** 2)) * -0.6
    subpolar   = np.exp(-((latitude - 0.75) ** 2) / (2 * 0.10 ** 2)) * 0.5

    lat_moisture = np.clip(0.5 + itcz * 0.5 + horse_dry + subpolar, 0.0, 1.0)

    # ── b) Ocean proximity ────────────────────────────────────────────────────
    ocean_bonus = np.zeros(len(centers))
    for cell_id, neighbors in adjacency.items():
        if not neighbors:
            continue
        if any(is_oceanic[n] for n in neighbors):
            ocean_bonus[cell_id] = 0.25     # coastal cells get moisture

    # Spread ocean moisture inward (2 hops)
    for hop in range(2):
        new_bonus = ocean_bonus.copy()
        for cell_id, neighbors in adjacency.items():
            if not neighbors:
                continue
            max_neighbor = max(ocean_bonus[n] for n in neighbors)
            new_bonus[cell_id] = max(ocean_bonus[cell_id], max_neighbor * 0.6)
        ocean_bonus = new_bonus

    # ── c) Orographic effect ──────────────────────────────────────────────────
    # Prevailing westerlies blow from West (–X direction on the sphere).
    # Windward: cells whose surface normal has a negative X component (facing –X).
    # We approximate windward face using x-component of center:
    # cells at negative x are "windward" of high terrain nearby.
    orographic = np.zeros(len(centers))

    # Rain shadow: if a high cell is to the windward side, subtract moisture
    for cell_id, neighbors in adjacency.items():
        if not neighbors:
            continue
        cx = centers[cell_id, 0]
        for n in neighbors:
            # Windward neighbor is one with more-negative x (further west)
            if centers[n, 0] < cx and heights[n] > heights[cell_id] + 0.2:
                # We are in rain shadow
                orographic[cell_id] -= 0.20
            elif centers[n, 0] > cx and heights[n] > heights[cell_id] + 0.2:
                # We are windward of high terrain → extra moisture
                orographic[cell_id] += 0.10

    moisture = lat_moisture + ocean_bonus + orographic
    return np.clip(moisture, 0.0, 1.0)


# ── Terrain classification ────────────────────────────────────────────────────

def classify_terrain(
    height:      float,
    temperature: float,
    moisture:    float,
    sea_level:   float,
) -> int:
    """Map climate parameters to one of the 19 GDD terrain types."""

    # ── Water ────────────────────────────────────────────────────────────────
    if height < sea_level - 0.5:
        return DEEP_OCEAN
    if height < sea_level - 0.15:
        return OCEAN
    if height < sea_level + 0.02:
        return COASTAL

    # ── Ice ──────────────────────────────────────────────────────────────────
    if temperature < 0.10:
        return POLAR_ICE

    # ── High altitude ─────────────────────────────────────────────────────────
    if height > 0.75:
        return MONTANE_IMPASSABLE
    if height > 0.50:
        return MONTANE

    # ── Sub-polar ─────────────────────────────────────────────────────────────
    if temperature < 0.22:
        return TUNDRA
    if temperature < 0.32:
        return TAIGA

    # ── Tropical ─────────────────────────────────────────────────────────────
    if temperature > 0.78:
        if moisture > 0.65: return TROPICAL
        if moisture > 0.50: return MONSOON
        if moisture > 0.28: return SAVANNA
        if moisture > 0.14: return DESERT
        return ARID_DESERT

    # ── Arid / steppe ────────────────────────────────────────────────────────
    if moisture < 0.15: return ARID_DESERT
    if moisture < 0.25: return DESERT
    if moisture < 0.35:
        return XERIC if temperature > 0.55 else DRY_STEPPE

    # ── Temperate ─────────────────────────────────────────────────────────────
    if temperature > 0.55 and moisture < 0.55: return MEDITERRANEAN
    if moisture > 0.65:                         return GRASSLAND
    return TEMPERATE


# ── Full climate pass ─────────────────────────────────────────────────────────

@dataclass
class ClimateResult:
    terrain:     np.ndarray    # (N,) int — terrain code per cell
    temperature: np.ndarray    # (N,) float [0,1]
    moisture:    np.ndarray    # (N,) float [0,1]


def apply_climate(
    sphere:    SphereData,
    tectonic:  TectonicResult,
) -> ClimateResult:

    log.info("Computing climate …")

    temp = compute_temperature(sphere.centers, tectonic.heights)
    moist = compute_moisture(
        sphere.centers,
        tectonic.heights,
        sphere.adjacency,
        tectonic.is_oceanic,
        tectonic.sea_level,
    )

    terrain = np.array([
        classify_terrain(
            float(tectonic.heights[i]),
            float(temp[i]),
            float(moist[i]),
            tectonic.sea_level,
        )
        for i in range(sphere.num_cells)
    ], dtype=np.int32)

    # Terrain type distribution
    unique, counts = np.unique(terrain, return_counts=True)
    breakdown = {int(u): int(c) for u, c in zip(unique, counts)}
    log.info("Terrain distribution: %s", breakdown)

    return ClimateResult(terrain=terrain, temperature=temp, moisture=moist)

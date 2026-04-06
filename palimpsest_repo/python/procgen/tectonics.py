"""
procgen/tectonics.py
~~~~~~~~~~~~~~~~~~~~
Full plate tectonic simulation on a spherical Voronoi world.

Pipeline:
  1. Plate generation  — Euler pole + angular velocity per plate
  2. Cell assignment   — each cell assigned to nearest plate seed
  3. Simulation loop   — N timesteps of plate motion; accumulate
                         convergence/divergence stress at boundaries
  4. Height assignment — boundary type (collision/subduction/rift)
                         drives initial height field
  5. Thermal erosion   — multiple diffusion passes smooth the landscape
  6. Hydraulic erosion — simplified flow / rain-shadow model
  7. Noise overlay     — fractal noise adds local terrain variation

All heavy computation is vectorised with numpy.
"""

from __future__ import annotations

import math
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from palimpsest.python.procgen.sphere import SphereData

log = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class TectonicConfig:
    num_plates:          int   = 14       # number of tectonic plates
    oceanic_fraction:    float = 0.60     # fraction of plates that are oceanic
    simulation_steps:    int   = 150      # timesteps of plate movement
    max_omega:           float = 0.008    # max angular velocity (rad / step)
    erosion_passes:      int   = 40       # thermal erosion iterations
    erosion_rate:        float = 0.18     # diffusion rate per erosion pass
    hydraulic_passes:    int   = 20       # hydraulic erosion iterations
    noise_octaves:       int   = 5        # fractal noise octaves
    noise_amplitude:     float = 0.22     # noise amplitude (fraction of height range)
    sea_level_percentile: float = 0.38    # fraction of cells that are ocean
    height_scale:        float = 0.08     # visual extrusion in Godot units per height unit

    # Height modifiers by boundary type
    continental_collision_uplift: float = 1.0   # both plates pushed up
    subduction_mountain_uplift:   float = 0.75  # continental side of subduction
    subduction_trench_depth:      float = -0.6  # oceanic side of subduction
    rift_valley_depth:            float = -0.15 # continental divergence
    mid_ocean_ridge_height:       float = 0.12  # oceanic divergence

    # Base elevations per plate type (relative to sea level = 0)
    oceanic_base_range:      tuple = (-0.7, -0.15)
    continental_base_range:  tuple = (0.05, 0.45)


# ── Plate dataclass ────────────────────────────────────────────────────────────

@dataclass
class Plate:
    id:           int
    seed_cell:    int
    is_oceanic:   bool
    euler_pole:   np.ndarray   # unit vector (3,)
    omega:        float         # angular velocity (rad/step); sign = CW vs CCW
    base_elev:    float         # baseline elevation for cells on this plate


# ── Step 1: Generate plates ───────────────────────────────────────────────────

def generate_plates(
    sphere: SphereData,
    config: TectonicConfig,
    rng: random.Random,
) -> list[Plate]:
    """
    Select plate seeds spread across the sphere (sub-Fibonacci sampling),
    assign random Euler poles and angular velocities.
    """
    P = min(config.num_plates, sphere.num_cells // 4)

    # Spread seeds by selecting every (N//P)th Fibonacci point
    step = max(1, sphere.num_cells // P)
    seeds = list(range(0, sphere.num_cells, step))[:P]

    # Shuffle slightly to break symmetry
    offsets = [rng.randint(-step // 4, step // 4) for _ in seeds]
    seeds = [max(0, min(sphere.num_cells - 1, s + o)) for s, o in zip(seeds, offsets)]
    seeds = list(dict.fromkeys(seeds))[:P]   # deduplicate

    plates: list[Plate] = []
    for i, seed in enumerate(seeds):
        is_oceanic = rng.random() < config.oceanic_fraction

        # Random Euler pole (rotation axis): unit vector
        pole = np.array([
            rng.gauss(0, 1),
            rng.gauss(0, 1),
            rng.gauss(0, 1),
        ])
        pole /= np.linalg.norm(pole)

        # Random angular velocity
        omega = rng.uniform(config.max_omega * 0.3, config.max_omega)
        omega *= rng.choice([-1, 1])   # CW or CCW

        lo, hi = config.oceanic_base_range if is_oceanic else config.continental_base_range
        base_elev = rng.uniform(lo, hi)

        plates.append(Plate(
            id         = i,
            seed_cell  = seed,
            is_oceanic = is_oceanic,
            euler_pole = pole,
            omega      = omega,
            base_elev  = base_elev,
        ))

    log.info(
        "Generated %d plates (%d oceanic, %d continental)",
        len(plates),
        sum(1 for p in plates if p.is_oceanic),
        sum(1 for p in plates if not p.is_oceanic),
    )
    return plates


# ── Step 2: Assign cells to plates ────────────────────────────────────────────

def assign_cells(
    sphere: SphereData,
    plates: list[Plate],
) -> np.ndarray:
    """
    Assign each cell to the nearest plate seed by great-circle (dot-product) distance.
    Returns plate_ids array of shape (N,).
    """
    seed_centers = sphere.centers[[p.seed_cell for p in plates]]   # (P, 3)
    # dot product = cos(angle); highest dot = nearest point on unit sphere
    dots = sphere.centers @ seed_centers.T    # (N, P)
    plate_ids = np.argmax(dots, axis=1)       # (N,)
    return plate_ids


# ── Step 3: Simulate plate motion ─────────────────────────────────────────────

def simulate_motion(
    sphere:    SphereData,
    plates:    list[Plate],
    plate_ids: np.ndarray,
    config:    TectonicConfig,
) -> np.ndarray:
    """
    Simulate T timesteps of plate motion using Euler-pole rotations.
    At each timestep, compute convergence (positive) / divergence (negative)
    at every plate boundary edge.

    Returns accumulated_stress array of shape (N,): net compression/extension
    per cell summed over all timesteps.
    """
    N = sphere.num_cells
    P = len(plates)
    T = config.simulation_steps

    # Pre-compute angular velocity vectors Ω = omega * pole for each plate
    Omega = np.array([p.omega * p.euler_pole for p in plates])   # (P, 3)

    # Pre-compute all cell velocities for each plate: V[p] = Ω[p] × centers
    # Shape: (P, N, 3)
    # v_i[p][c] = cross(Omega[p], centers[c])
    # vectorised: np.cross broadcasts over last dimension
    cell_velocities = np.cross(Omega[:, np.newaxis, :], sphere.centers[np.newaxis, :, :])   # (P, N, 3)

    # Each cell's actual velocity = cell_velocities[plate_ids[c], c]
    actual_velocities = cell_velocities[plate_ids, np.arange(N)]   # (N, 3)

    # Boundary edges: pairs (a, b) where plates differ
    edges = np.array([
        (a, b) for (a, b) in sphere.boundary_edges
        if plate_ids[a] != plate_ids[b]
    ], dtype=np.int32)

    if len(edges) == 0:
        log.warning("No plate boundary edges found — is num_plates too large?")
        return np.zeros(N)

    log.info("Simulating %d timesteps across %d boundary edges …", T, len(edges))

    ea, eb = edges[:, 0], edges[:, 1]

    # Midpoints on unit sphere
    mid_raw = sphere.centers[ea] + sphere.centers[eb]
    mid_norms = np.linalg.norm(mid_raw, axis=1, keepdims=True)
    midpoints = mid_raw / mid_norms                               # (E, 3)

    # Boundary tangent direction (in tangent plane at midpoint, pointing b→a direction)
    n_raw = sphere.centers[eb] - sphere.centers[ea]
    proj  = np.sum(n_raw * midpoints, axis=1, keepdims=True) * midpoints
    n_tangent = n_raw - proj
    n_norms = np.linalg.norm(n_tangent, axis=1, keepdims=True)
    # Avoid divide by zero
    safe_norms = np.where(n_norms < 1e-10, 1.0, n_norms)
    n_tangent = n_tangent / safe_norms                            # (E, 3)

    # Velocities at midpoints for each plate: Ω × midpoint
    # (P, E, 3)
    mid_velocities = np.cross(Omega[:, np.newaxis, :], midpoints[np.newaxis, :, :])

    # For each edge, velocity of plate_a and plate_b at the midpoint
    plate_a = plate_ids[ea]   # (E,)
    plate_b = plate_ids[eb]   # (E,)

    v_a = mid_velocities[plate_a, np.arange(len(edges))]   # (E, 3)
    v_b = mid_velocities[plate_b, np.arange(len(edges))]   # (E, 3)
    v_rel = v_a - v_b                                       # (E, 3)

    # Convergence rate: positive = converging, negative = diverging
    convergence = np.sum(v_rel * n_tangent, axis=1)         # (E,)

    # Accumulate stress over T timesteps (rates are constant; multiply by T)
    # We scale by T so the magnitude is comparable regardless of step count
    stress_per_edge = convergence * T

    accumulated = np.zeros(N)
    np.add.at(accumulated, ea, stress_per_edge)
    np.add.at(accumulated, eb, stress_per_edge)

    log.info("Stress range: [%.3f, %.3f]", accumulated.min(), accumulated.max())
    return accumulated


# ── Step 4: Height from stress + plate type ───────────────────────────────────

def compute_heights(
    sphere:     SphereData,
    plates:     list[Plate],
    plate_ids:  np.ndarray,
    stress:     np.ndarray,
    config:     TectonicConfig,
) -> np.ndarray:
    """
    Convert accumulated boundary stress into a height field.

    Rules per boundary-type:
      Continental × Continental convergence → mountain range (both cells high)
      Continental × Oceanic convergence     → coastal mountain (continental) + trench (oceanic)
      Oceanic × Oceanic convergence         → mild ridge (both)
      Any divergence                        → rift / mid-ocean ridge
    """
    N = sphere.num_cells
    heights = np.array([plates[pid].base_elev for pid in plate_ids])   # (N,)

    plate_oceanic = np.array([p.is_oceanic for p in plates])

    for a, b in sphere.boundary_edges:
        pid_a = plate_ids[a]
        pid_b = plate_ids[b]
        if pid_a == pid_b:
            continue

        # Average convergence at this edge (stored on both cells)
        conv = (stress[a] + stress[b]) * 0.5
        is_oc_a = plate_oceanic[pid_a]
        is_oc_b = plate_oceanic[pid_b]

        if conv > 0:   # converging
            if not is_oc_a and not is_oc_b:
                # Continental collision → high mountains both sides
                delta = conv * config.continental_collision_uplift * 0.001
                heights[a] += delta
                heights[b] += delta

            elif not is_oc_a and is_oc_b:
                # Subduction: oceanic b dives under continental a
                heights[a] += conv * config.subduction_mountain_uplift  * 0.001
                heights[b] += conv * config.subduction_trench_depth     * 0.001

            elif is_oc_a and not is_oc_b:
                # Subduction: oceanic a dives under continental b
                heights[a] += conv * config.subduction_trench_depth     * 0.001
                heights[b] += conv * config.subduction_mountain_uplift  * 0.001

            else:
                # Oceanic–oceanic: mild ridge
                delta = conv * config.mid_ocean_ridge_height * 0.0005
                heights[a] += delta
                heights[b] += delta

        else:   # diverging (conv < 0)
            if not is_oc_a and not is_oc_b:
                # Continental rift
                delta = abs(conv) * config.rift_valley_depth * 0.001
                heights[a] -= delta
                heights[b] -= delta
            else:
                # Mid-ocean ridge
                delta = abs(conv) * config.mid_ocean_ridge_height * 0.0005
                heights[a] += delta
                heights[b] += delta

    return heights


# ── Step 5: Thermal erosion ───────────────────────────────────────────────────

def thermal_erosion(
    heights:   np.ndarray,
    adjacency: dict[int, list[int]],
    passes:    int,
    rate:      float,
) -> np.ndarray:
    """
    Iterative height diffusion. High-relief areas erode into neighbours.
    Rate scales with local gradient (steeper = faster erosion).
    """
    h = heights.copy()
    adj_arr = [np.array(v, dtype=np.int32) for v in adjacency.values()]

    for _ in range(passes):
        new_h = h.copy()
        for cell_id, neighbors in adjacency.items():
            if not neighbors:
                continue
            neighbor_h = h[neighbors]
            gradient   = h[cell_id] - neighbor_h
            # Only erode where cell is higher than neighbours
            erosion    = np.clip(gradient, 0, None) * rate
            new_h[cell_id]   -= erosion.sum()
            new_h[neighbors] += erosion
        h = new_h

    return h


# ── Step 6: Hydraulic erosion (simplified) ───────────────────────────────────

def hydraulic_erosion(
    heights:   np.ndarray,
    centers:   np.ndarray,
    adjacency: dict[int, list[int]],
    passes:    int,
    sea_level: float,
) -> np.ndarray:
    """
    Simplified hydraulic erosion:
    - Rainfall proportional to latitude band and orographic effects
    - Water flows downhill, carrying sediment proportional to slope
    - Sediment deposited where flow slows (flat areas, coastlines)
    """
    h         = heights.copy()
    sediment  = np.zeros_like(h)
    RAIN_RATE = 0.04
    CAPACITY  = 0.6    # max sediment water can carry
    DEPOSIT   = 0.3    # fraction deposited when slope decreases

    for _ in range(passes):
        # Rainfall: higher near equator (|z| small), reduced by rain shadow
        latitude = np.abs(centers[:, 2])
        rainfall = RAIN_RATE * (1.0 - latitude * 0.8)
        rainfall[h < sea_level] = 0.0   # no surface rain in deep ocean

        water = rainfall.copy()
        new_h   = h.copy()
        new_sed = sediment.copy()

        for cell_id, neighbors in adjacency.items():
            if not neighbors or water[cell_id] < 1e-6:
                continue
            neighbor_h = h[neighbors]
            deltas     = h[cell_id] - neighbor_h
            flow_mask  = deltas > 0
            if not flow_mask.any():
                # Deposit sediment in flat/basin areas
                deposit = sediment[cell_id] * DEPOSIT
                new_h[cell_id]  += deposit
                new_sed[cell_id] -= deposit
                continue

            flow_neighbors = np.array(neighbors)[flow_mask]
            slopes         = deltas[flow_mask]
            total_slope    = slopes.sum()

            for ni, slope in zip(flow_neighbors, slopes):
                fraction   = slope / total_slope
                w_flow     = water[cell_id] * fraction
                # Sediment capacity proportional to slope
                carry_cap  = slope * CAPACITY * w_flow
                excess_sed = max(0, sediment[cell_id] - carry_cap)
                # Erode if carrying below capacity
                erode      = max(0, (carry_cap - sediment[cell_id]) * 0.1)

                new_h[cell_id]  -= erode
                new_h[ni]       += excess_sed * DEPOSIT
                new_sed[cell_id] += erode - excess_sed * DEPOSIT

        h        = new_h
        sediment = np.clip(new_sed, 0, None)

    return h


# ── Step 7: Noise overlay ─────────────────────────────────────────────────────

def _value_noise_sphere(centers: np.ndarray, seed: int, scale: float) -> np.ndarray:
    """
    Cheap per-cell noise using hashed sphere coordinates.
    Returns values in [-1, 1].
    """
    rng = np.random.default_rng(seed)
    # Random frequency components on the sphere
    num_freq = 32
    axes  = rng.standard_normal((num_freq, 3))
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    freqs = rng.uniform(1.0, 4.0, num_freq) * scale
    phases = rng.uniform(0, 2 * math.pi, num_freq)

    noise = np.zeros(len(centers))
    amplitude = 1.0
    total_amp = 0.0
    for i in range(num_freq):
        dots  = centers @ axes[i]
        noise += np.sin(dots * freqs[i] + phases[i]) * amplitude
        total_amp += amplitude
        amplitude *= 0.55

    return noise / total_amp


def add_noise(
    heights:  np.ndarray,
    centers:  np.ndarray,
    config:   TectonicConfig,
    seed:     int,
) -> np.ndarray:
    noise = _value_noise_sphere(centers, seed, scale=3.0)
    height_range = heights.max() - heights.min()
    return heights + noise * height_range * config.noise_amplitude


# ── Sea level ─────────────────────────────────────────────────────────────────

def compute_sea_level(heights: np.ndarray, percentile: float) -> float:
    """Set sea level so that `percentile` fraction of cells are ocean."""
    return float(np.percentile(heights, percentile * 100))


# ── Full pipeline ─────────────────────────────────────────────────────────────

@dataclass
class TectonicResult:
    heights:    np.ndarray            # (N,)  final height, sea_level = 0
    plate_ids:  np.ndarray            # (N,)  int
    plates:     list[Plate]
    sea_level:  float                 # absolute height value at ocean boundary
    is_oceanic: np.ndarray            # (N,) bool  height < sea_level


def run_simulation(
    sphere: SphereData,
    config: TectonicConfig | None = None,
    seed:   int = 0,
) -> TectonicResult:
    """
    Full tectonic pipeline. All steps in sequence.
    """
    if config is None:
        config = TectonicConfig()

    rng = random.Random(seed)

    log.info("=== Tectonic simulation start ===")

    plates    = generate_plates(sphere, config, rng)
    plate_ids = assign_cells(sphere, plates)
    stress    = simulate_motion(sphere, plates, plate_ids, config)

    log.info("Computing initial height field …")
    heights = compute_heights(sphere, plates, plate_ids, stress, config)

    log.info("Thermal erosion (%d passes) …", config.erosion_passes)
    heights = thermal_erosion(heights, sphere.adjacency, config.erosion_passes, config.erosion_rate)

    sea_level_raw = compute_sea_level(heights, config.sea_level_percentile)

    log.info("Hydraulic erosion (%d passes) …", config.hydraulic_passes)
    heights = hydraulic_erosion(heights, sphere.centers, sphere.adjacency, config.hydraulic_passes, sea_level_raw)

    log.info("Adding fractal noise …")
    heights = add_noise(heights, sphere.centers, config, seed + 1)

    sea_level = compute_sea_level(heights, config.sea_level_percentile)

    # Normalise to [-1, 1] with sea_level = 0
    h_min = heights.min()
    h_max = heights.max()
    heights = (heights - sea_level) / max(h_max - h_min, 1e-6) * 2.0
    sea_level_norm = 0.0   # by definition after normalisation

    is_oceanic = heights < sea_level_norm

    log.info(
        "=== Tectonic done: %.1f%% ocean, height range [%.3f, %.3f] ===",
        is_oceanic.mean() * 100,
        heights.min(),
        heights.max(),
    )

    return TectonicResult(
        heights   = heights,
        plate_ids = plate_ids,
        plates    = plates,
        sea_level = sea_level_norm,
        is_oceanic = is_oceanic,
    )

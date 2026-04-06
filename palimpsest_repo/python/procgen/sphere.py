"""
procgen/sphere.py
~~~~~~~~~~~~~~~~~
Fibonacci-sphere point distribution → scipy SphericalVoronoi → adjacency graph.

The Fibonacci (golden-ratio) spiral produces the most uniform point
distribution on a sphere without clustering at poles. Each point becomes
the seed of a Voronoi cell. The resulting irregular polygons are the
tiles of The Palimpsest world.

Cell addressing uses integer cell_id (index into the points array).
All coordinates are on the UNIT sphere; callers scale by sphere_radius.

Sphere radius scales as  R = BASE_RADIUS * sqrt(N / BASE_N)
so that apparent cell size stays roughly constant across cell counts.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import SphericalVoronoi, ConvexHull

log = logging.getLogger(__name__)

BASE_RADIUS = 10.0   # Godot units at 1000 cells
BASE_N      = 1000


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class SphereData:
    """All geometric data for the world sphere."""
    num_cells:     int
    sphere_radius: float                         # Godot-unit radius
    centers:       np.ndarray                    # (N, 3)  unit sphere
    vertices:      np.ndarray                    # (V, 3)  Voronoi vertices, unit sphere
    regions:       list[list[int]]               # cell_id → [vertex indices], sorted
    adjacency:     dict[int, list[int]]          # cell_id → [neighbor cell_ids]
    boundary_edges: list[tuple[int, int]]        # all (a, b) pairs where a < b


# ── Fibonacci sphere ──────────────────────────────────────────────────────────

def fibonacci_sphere(n: int) -> np.ndarray:
    """
    Generate N evenly-spaced points on the unit sphere using the
    Fibonacci / golden-ratio spiral method.

    Returns shape (N, 3) float64 array. Points are on the unit sphere.
    """
    phi = (1.0 + math.sqrt(5.0)) / 2.0   # golden ratio

    i = np.arange(n, dtype=np.float64)
    theta = 2.0 * math.pi * i / phi       # azimuthal angle, spirals by φ each step
    z     = 1.0 - (2.0 * i + 1.0) / n    # z ∈ (-1, 1), linear pole-to-pole sweep
    r     = np.sqrt(np.clip(1.0 - z * z, 0.0, 1.0))

    x = r * np.cos(theta)
    y = r * np.sin(theta)

    points = np.column_stack([x, y, z])
    # Normalise to handle any floating-point drift
    norms = np.linalg.norm(points, axis=1, keepdims=True)
    return points / norms


# ── Adjacency ─────────────────────────────────────────────────────────────────

def _build_adjacency(regions: list[list[int]], num_cells: int) -> tuple[dict[int, list[int]], list[tuple[int, int]]]:
    """
    Two cells are adjacent iff they share ≥ 2 Voronoi vertices (an edge).

    Build:
      adjacency:      cell_id → sorted list of neighbor cell_ids
      boundary_edges: sorted list of (a, b) pairs with a < b
    """
    # vertex → set of cells containing it
    vertex_to_cells: dict[int, set[int]] = {}
    for cell_id, region in enumerate(regions):
        for v in region:
            vertex_to_cells.setdefault(v, set()).add(cell_id)

    adjacency:      dict[int, set[int]] = {i: set() for i in range(num_cells)}
    boundary_edges: set[tuple[int, int]] = set()

    # For each vertex, all cells sharing it are pairwise candidates for adjacency.
    # Two cells sharing ≥ 2 vertices share an edge.
    shared_count: dict[tuple[int, int], int] = {}
    for cells in vertex_to_cells.values():
        cells_list = sorted(cells)
        for i in range(len(cells_list)):
            for j in range(i + 1, len(cells_list)):
                key = (cells_list[i], cells_list[j])
                shared_count[key] = shared_count.get(key, 0) + 1

    for (a, b), count in shared_count.items():
        if count >= 2:
            adjacency[a].add(b)
            adjacency[b].add(a)
            boundary_edges.add((a, b))

    adj_sorted = {k: sorted(v) for k, v in adjacency.items()}
    edges_sorted = sorted(boundary_edges)
    return adj_sorted, edges_sorted


# ── Main builder ──────────────────────────────────────────────────────────────

def build_sphere(num_cells: int, seed: int = 0) -> SphereData:
    """
    Full pipeline: Fibonacci points → SphericalVoronoi → adjacency.

    num_cells: target number of Voronoi cells (500–1500 recommended)
    seed:      not used for determinism (Fibonacci is deterministic),
               kept for API consistency with other procgen modules.
    """
    log.info("Building sphere: %d cells …", num_cells)

    sphere_radius = BASE_RADIUS * math.sqrt(num_cells / BASE_N)

    # 1. Generate seed points
    centers = fibonacci_sphere(num_cells)

    # 2. Compute spherical Voronoi diagram
    sv = SphericalVoronoi(
        centers,
        radius=1.0,
        center=np.zeros(3),
        threshold=1e-10,
    )
    sv.sort_vertices_of_regions()

    regions: list[list[int]] = [list(r) for r in sv.regions]
    vertices: np.ndarray     = sv.vertices

    # 3. Build adjacency
    adjacency, boundary_edges = _build_adjacency(regions, num_cells)

    avg_neighbors = sum(len(v) for v in adjacency.values()) / max(num_cells, 1)
    log.info(
        "Sphere built: %d cells, %d Voronoi vertices, %.2f avg neighbors, radius=%.2f",
        num_cells, len(vertices), avg_neighbors, sphere_radius,
    )

    return SphereData(
        num_cells      = num_cells,
        sphere_radius  = sphere_radius,
        centers        = centers,
        vertices       = vertices,
        regions        = regions,
        adjacency      = adjacency,
        boundary_edges = boundary_edges,
    )


# ── Serialisation helpers ─────────────────────────────────────────────────────

def cell_vertices_sorted(sphere: SphereData, cell_id: int) -> list[list[float]]:
    """
    Return the polygon vertices of a cell, sorted into winding order
    on the sphere surface (counter-clockwise when viewed from outside).
    """
    region = sphere.regions[cell_id]
    if not region:
        return []
    center = sphere.centers[cell_id]
    verts  = sphere.vertices[region]            # (M, 3)

    # Project vertices onto tangent plane at center
    # u = arbitrary tangent 1, w = center × u (tangent 2)
    u = np.array([1, 0, 0], dtype=float)
    if abs(np.dot(center, u)) > 0.9:
        u = np.array([0, 1, 0], dtype=float)
    u -= np.dot(u, center) * center
    u /= np.linalg.norm(u)
    w = np.cross(center, u)

    angles = [math.atan2(float(np.dot(v - center, w)), float(np.dot(v - center, u))) for v in verts]
    sorted_verts = [verts[i].tolist() for i in np.argsort(angles)]
    return sorted_verts


def sphere_to_wire(sphere: SphereData) -> dict[str, Any]:
    """
    Compact representation for the bridge payload.
    Centers and vertices are on the UNIT sphere; Godot scales by sphere_radius.
    """
    return {
        "num_cells":    int(sphere.num_cells),
        "sphere_radius": float(sphere.sphere_radius),
        "centers":      sphere.centers.tolist(),
        "vertices":     sphere.vertices.tolist(),
        "regions":      [[int(v) for v in r] for r in sphere.regions],
        "adjacency":    {str(int(k)): [int(n) for n in v] for k, v in sphere.adjacency.items()},
    }

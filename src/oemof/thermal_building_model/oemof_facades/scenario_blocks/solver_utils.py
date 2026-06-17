"""Shared helpers for the block-style advanced investment example scripts.

The helpers in this file are intentionally small and explicit:
- solver discovery and deterministic solve
- shared carrier/grid infrastructure
- small result utilities
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
from oemof import solph
from pyomo import environ as po

from oemof.thermal_building_model.oemof_facades.scenario_blocks.advanced_investment_blocks import (
    add_main_grids_and_carriers_block,
)


def find_available_solver(preferred: Optional[str] = "gurobi") -> str:
    """Return a usable LP-based solver name for solph model.solve(...)."""
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(["gurobi", "cbc", "glpk"])
    # Keep order while removing duplicates.
    seen = set()
    ordered = []
    for name in candidates:
        if name not in seen:
            ordered.append(name)
            seen.add(name)

    for solver_name in ordered:
        solver = po.SolverFactory(solver_name, solver_io="lp")
        try:
            if solver.available(exception_flag=False):
                return solver_name
        except Exception:
            continue
    raise RuntimeError(
        "No LP solver available (checked: gurobi, cbc, glpk). "
        "Install at least one solver."
    )


def solve_model(
    es: solph.EnergySystem,
    solver: str,
    co2_limit: float | None = None,
) -> Dict[str, Any]:
    """Build and solve a solph model and return status/meta/results."""
    model = solph.Model(es)
    if co2_limit is not None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=float(co2_limit))
    cmdline_options = {}
    if solver == "gurobi":
        # Keep deterministic behavior across runs.
        cmdline_options = {"MIPGap": 0, "Threads": 1, "Seed": 0}

    solve_result = model.solve(
        solver=solver,
        solve_kwargs={"tee": False},
        cmdline_options=cmdline_options,
    )
    termination = str(solve_result.solver.termination_condition).lower()
    if termination not in {"optimal", "feasible"}:
        raise RuntimeError(
            f"Solver did not return a feasible/optimal solution (termination={termination})."
        )

    meta = solph.processing.meta_results(model)
    results = solph.processing.results(model)
    return {
        "model": model,
        "results": results,
        "objective": float(meta["objective"]),
        "termination": termination,
        "solve_result": solve_result,
    }


def add_main_grids_and_carriers(
    es: solph.EnergySystem,
    peak_limit_kw: Optional[float] = None,
    include_hydrogen: bool = True,
) -> Dict[str, Any]:
    """Backward-compatible wrapper around the dedicated scenario block API."""
    return add_main_grids_and_carriers_block(
        es=es,
        peak_limit_kw=peak_limit_kw,
        include_hydrogen=include_hydrogen,
    )


def sum_node_flow(results: Dict[str, Any], node_label: str) -> float:
    """Sum all flow sequence columns for one node label."""
    sequences = solph.views.node(results, node_label)["sequences"]
    flow_cols = [col for col in sequences.columns if col[1] == "flow"]
    if not flow_cols:
        return 0.0
    return float(sequences[flow_cols].sum().sum())


def compute_total_co2_from_grids(
    electricity_post: Dict[str, Any],
    natural_gas_post: Dict[str, Any],
    bio_gas_post: Dict[str, Any],
    hydrogen_post: Optional[Dict[str, Any]] = None,
) -> float:
    """Compute total direct grid-related CO2."""
    total = (
        float(electricity_post["flow_from_grid_co2"] or 0.0)
        - float(electricity_post["flow_into_grid_co2"] or 0.0)
        + float(natural_gas_post["flow_from_grid_co2"] or 0.0)
        + float(bio_gas_post["flow_from_grid_co2"] or 0.0)
    )
    if hydrogen_post is not None:
        total += float(hydrogen_post["flow_from_grid_co2"] or 0.0)
    return total


def as_array(values: Any, n_steps: int) -> np.ndarray:
    """Return values as numpy array and validate length."""
    arr = np.asarray(values, dtype=float)
    if arr.shape[0] != n_steps:
        raise ValueError(f"Expected length {n_steps}, got {arr.shape[0]}.")
    return arr

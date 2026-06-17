import pytest


def _iter_solver_factories():
    po = pytest.importorskip("pyomo.environ")
    for solver_name in ("gurobi", "cbc", "glpk", "highs"):
        yield solver_name, po.SolverFactory(solver_name, solver_io="lp")


@pytest.fixture(scope="session")
def available_solver():
    """Return the first available MILP solver used by solver-backed tests."""
    for solver_name, solver in _iter_solver_factories():
        try:
            if solver.available(exception_flag=False):
                return solver_name
        except Exception:
            continue
    pytest.skip("No MILP solver available (checked: gurobi, cbc, glpk, highs).")


def _deterministic_solver_options(solver_name):
    if solver_name == "gurobi":
        return {"MIPGap": 0, "Threads": 1, "Seed": 0}
    return {}


@pytest.fixture
def solver_cmdline_options():
    """Return deterministic solver options for the requested solver."""

    def _options(solver_name):
        return _deterministic_solver_options(solver_name)

    return _options


@pytest.fixture
def solve_solph_model():
    """Build and solve a solph model deterministically where possible."""
    solph = pytest.importorskip("oemof.solph")

    def _solve(es, solver_name):
        model = solph.Model(es)
        solve_result = model.solve(
            solver=solver_name,
            solve_kwargs={"tee": False},
            cmdline_options=_deterministic_solver_options(solver_name),
        )
        termination = str(solve_result.solver.termination_condition).lower()
        assert termination in {"optimal", "feasible"}
        results = solph.processing.results(model)
        meta = solph.processing.meta_results(model)
        return model, results, float(meta["objective"])

    return _solve


@pytest.fixture
def sum_node_flow():
    """Return helper to sum all flow sequence columns for one node label."""
    solph = pytest.importorskip("oemof.solph")

    def _sum(results, node_label):
        sequences = solph.views.node(results, node_label)["sequences"]
        flow_cols = [col for col in sequences.columns if col[1] == "flow"]
        if not flow_cols:
            return 0.0
        return float(sequences[flow_cols].sum().sum())

    return _sum

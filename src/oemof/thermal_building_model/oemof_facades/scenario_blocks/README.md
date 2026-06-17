# Scenario Block Library (Advanced Investment)

## Recommendation and placement decision

For this repository, scenario-generation blocks should live under:

`oemof_facades/scenario_blocks/`

Why this is the best fit here:

- Domain primitives already live in `oemof_facades/infrastructure/`, `oemof_facades/technologies/`, and `oemof_facades/refurbishment/`.
- Scenario assembly is a separate concern from primitive object definitions.
- Keeping blocks in `src/` (not inside one example script) makes them discoverable and reusable across decentralized, centralized, and future examples.
- Example scripts stay readable because they become "sequence of blocks" runners.

This keeps a clean split:

- **Primitives**: carriers, grids, demands, technologies.
- **Composition**: scenario blocks that wire primitives into a concrete system.

## Canonical modules

- `advanced_investment_blocks.py`: block functions that add grids/demands/technologies and scenario wiring.
- `solver_utils.py`: deterministic solve helpers and shared post-processing utilities used by block-based scripts.
- `workflow_preprocessing.py`: reusable district/scenario preprocessing and deterministic toy input preparation.
- `constraint_reduction_workflow.py`: reusable stepwise CO2/peak tightening loop with optional result persistence.

## Naming and interface convention

Use:

- `add_<thing>_block(...) -> dict`

Minimum expectations for every new block:

1. First argument is always `es: solph.EnergySystem`.
2. Function adds all created nodes/components to `es` (single side effect).
3. Function returns a dictionary with references to created dataclasses/components/buses.
4. Naming is explicit and scenario-readable (e.g. `add_heat_grid_investment_block`).

Notes:

- For backward compatibility, some older helpers without `_block` suffix still exist.
- New code should prefer `_block` functions.

## How to add a new block

1. Add function in `advanced_investment_blocks.py` with `add_<name>_block`.
2. Keep parameters explicit (no hidden globals).
3. Return a dictionary with stable keys.
4. Update example workflow scripts to call the new block in sequence.
5. Add or extend tests that assert the block is present in labels/results.

For preprocessing and iterative loops:

1. Put district/scenario input assembly in `workflow_preprocessing.py`.
2. Put repeated solve-loop logic (CO2/peak tightening) in `constraint_reduction_workflow.py`.
3. Keep script-level `run_model` focused on: preprocess -> build -> solve -> extract.
4. Keep script-level `run_stepwise_workflow` focused on: call loop helper + save path selection.

## Example: small extension block

`add_heat_dump_block` is included as a minimal example:

- Input: `es`, `input_bus`, `label`.
- Side effect: adds a sink to absorb heat.
- Return: `{"sink": sink}`.

# Applied energy optimization post-processing

This folder post-processes the decentralized optimization results generated in
`03_applied_energy_optimization`, in particular the workflow
`decentralized_supply_single_building_multiple_heat_carrier_levels`.

The objective is to transform building-level optimization outputs into combined
Pareto-front data sets that can be used for subsequent scientific evaluation.
The scripts aggregate decentralized single-building results for selected SFH and
MFH cluster combinations, extract non-dominated solution sets, and prepare
figures for the interpretation of system-level trade-offs between greenhouse
gas emissions, peak grid exchange power, and total annualized costs.

## Workflow

1. `a_post_process_decentralized_k_combinations.py`
   combines decentralized single-building optimization results into
   cluster-combination Pareto fronts. The resulting post-processed folders are
   the main data source for the downstream analyses.
2. `b_plot_pareto_front_dec.py`
   visualizes the decentralized Pareto fronts and supports the inspection of
   representative trade-off points.
3. `c_plot_dec_compare_extreme_tradeoff_deviations.py`
   compares selected extreme trade-off solutions and quantifies deviations from
   reference cases.

The files with an `x_` prefix are retained as auxiliary or superseded analysis
scripts. They are not part of the main workflow described above.


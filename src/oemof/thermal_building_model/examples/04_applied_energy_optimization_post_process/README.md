# Applied energy optimization post-processing

This folder post-processes the optimization results generated in
`03_applied_energy_optimization`. It contains separate branches for the
decentralized building-level workflow and the centralized district-level
workflow used in the Applied Energy manuscript and thesis analyses.

The objective is to transform raw optimization output files into stable,
documented post-processed data sets that can be used for scientific evaluation.
For decentralized cases, single-building optimization results are aggregated
into combined district Pareto fronts. For centralized cases, district-level
result records are consolidated into one front-like package per cluster and
temperature-level case.

## Decentralized workflow

1. `decentralized/a_post_process_decentralized_k_combinations.py`
   combines decentralized single-building optimization results into
   cluster-combination Pareto fronts. The resulting post-processed folders are
   the main data source for the downstream analyses.
2. `b_plot_pareto_front_dec.py`
   visualizes the decentralized Pareto fronts and supports the inspection of
   representative trade-off points.
3. `c_plot_dec_compare_extreme_tradeoff_deviations.py`
   compares selected extreme trade-off solutions and quantifies deviations from
   reference cases.

## Centralized workflow

1. `centralized/a_post_process_centralized_results.py`
   loads centralized district-level result records, filters invalid result
   files, and writes consolidated centralized front packages.

Generated post-processed folders, plots, runtime tables, and diagnostics are
not part of the repository state. They should be regenerated from the scripts
or stored externally with the corresponding thesis or manuscript artifact.

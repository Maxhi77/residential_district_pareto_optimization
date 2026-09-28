# Applied energy Pareto-set analysis

This folder contains the downstream analysis of the post-processed optimization
results from `03_applied_energy_optimization` and
`04_applied_energy_optimization_post_process`. The main inputs are combined
decentralized Pareto fronts and, where required, consolidated centralized
front packages.

The objective is to evaluate how the number of SFH and MFH clusters affects the
quality and interpretability of the aggregated Pareto sets. The analysis
combines hypervolume-based convergence indicators, distance measures against a
reference Pareto set, energy-specific building KPIs, and publication-oriented
visualizations.

## Shared preparation

1. `c_iterate_over_clusters_and_calculate_demands.py`
   calculates electricity, domestic hot water, space-heating, and PV-potential
   profiles for each selected cluster and for the full reference UEU.
2. `b_create_reference_ueu_excel.py`
   summarizes reference UEU characteristics and energy KPIs in tabular form.

## Decentralized Pareto-set analysis

1. `decentralized/a_calculate_delta_hypervolume_over_k.py`
   evaluates the combined Pareto fronts over different cluster counts. It
   computes normalized hypervolume, delta hypervolume over increasing `k`, delta
   hypervolume against the reference/reference combination, and IGD against the
   reference Pareto set.
2. `decentralized/d_plot_delta_hypervolume_decentralized_combinations.py`
   creates heatmaps and comparison figures for delta hypervolume and IGD over
   SFH/MFH cluster-count combinations.
3. `e_plot_energy_specific_kpis_over_k.py`
   visualizes energy-specific KPIs over the number of clusters.
4. `decentralized/f_plot_pareto_front_projections_over_k.py`
   plots two-dimensional projections of selected Pareto fronts to support the
   comparison of approximation quality across cluster resolutions.
5. `g_plot_reference_kpi_comparison.py`
   optionally compares reference, SFH-reference, MFH-reference, and combined
   reference KPI profiles.

## Centralized Pareto-set analysis

1. `centralized/a_calculate_delta_hypervolume_centralized_over_k.py`
   evaluates centralized post-processed fronts over selected SFH/MFH cluster
   combinations and temperature levels.
2. `centralized/d_plot_delta_hypervolume_centralized_combinations.py`
   creates centralized delta-hypervolume and IGD comparison figures.
3. `centralized/f_plot_pareto_front_projections_centralized_over_k.py`
   creates selected centralized Pareto-front projection figures.

The alphabetic prefixes provide a stable file ordering in the directory. They
do not define a single linear execution order, because the KPI and Pareto-set
analyses form partly independent branches.

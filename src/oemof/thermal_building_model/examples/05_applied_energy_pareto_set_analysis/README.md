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

These scripts form part of the computational research artifact accompanying
the PhD dissertation. They expose the processing steps used to interpret
optimization results. Independently generated results can be analysed with the
same framework when the input paths, case selections, and expected package
structures are aligned. Several paths remain explicit source settings because
the scripts retain the configuration of the research analyses.

## Dependencies between stages

There are two partly independent branches:

- **Pareto-set comparisons:** raw optimization results are combined or
  consolidated in `04_applied_energy_optimization_post_process`, then read by
  the `a_calculate_*` scripts, and finally visualized by the corresponding
  `d_plot_*` and `f_plot_*` scripts. Comparisons against a full reference set
  require the corresponding reference-result packages in addition to the
  clustered results.
- **Energy-profile and building KPIs:** processed building and household inputs
  are used to prepare `demands_and_pv_potential.pkl` caches and reference
  workbooks; the energy-KPI and reference-comparison scripts consume those
  artifacts. These caches are distinct from optimization result packages.

For the upstream inputs and output layouts, see the
[optimization guide](../03_applied_energy_optimization/README.md) and the
[post-processing guide](../04_applied_energy_optimization_post_process/README.md).

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

## Configuring paths for locally generated results

The source-level settings below determine which artifacts are read and where
new artifacts are written. A research archive path does not imply that its
contents are distributed with this checkout. Replace it with the local result
root and select only cases for which the required inputs are available.

| Script | Input selection | Output selection |
| --- | --- | --- |
| `decentralized/a_calculate_delta_hypervolume_over_k.py` | `INPUT_BASE_DIR`, `UEU_CASES_TO_PROCESS`, `POST_PROCESS_NAME`; reads `combined_front.pkl` from SFH/MFH combination folders. | `OUTPUT_BASE_DIR`. |
| `centralized/a_calculate_delta_hypervolume_centralized_over_k.py` | `INPUT_BASE_DIR`, `UEU_CASES_TO_PROCESS`, `TEMPERATURE_LEVELS_TO_PROCESS`; reads `centralized_front.pkl` from consolidated case/cluster/temperature/group folders. | `OUTPUT_BASE_DIR`. |
| `decentralized/d_plot_delta_hypervolume_decentralized_combinations.py` | Its argument parser exposes the analysis-root selection; defaults include `DEFAULT_BASE_DIR` and the post-processing folder pattern. | `DEFAULT_PLOT_OUTPUT_ROOT` and the corresponding output argument. |
| `centralized/d_plot_delta_hypervolume_centralized_combinations.py` | `DEFAULT_ANALYSIS_ROOT`, selected UEUs, and temperature/group settings. It uses the shared decentralized plotting script for parts of the visualization. | Output settings passed to the shared plotting workflow and configured panel exports. |
| `decentralized/f_plot_pareto_front_projections_over_k.py`, `centralized/f_plot_pareto_front_projections_centralized_over_k.py` | `DEFAULT_BASE_DIR` and script-specific case/front selections. | `DEFAULT_OUTPUT_ROOT` and `DEFAULT_COMBINED_PANEL_DIR`. |
| `c_iterate_over_clusters_and_calculate_demands.py` | `EXAMPLES_BASE_DIR`, `UEU_CASES_TO_PROCESS`, and the required no-EV/EV profiles. | `OUTPUT_FILENAME`, written within the selected case/cluster input tree. |
| `b_create_reference_ueu_excel.py` | `EXAMPLES_BASE_DIR`, `UEU_CASES_TO_PROCESS`, and reference profile/building inputs. | `OUTPUT_DIR`; the default is this analysis directory. |
| `e_plot_energy_specific_kpis_over_k.py` | `EXAMPLES_BASE_DIR`, with `demands_and_pv_potential.pkl` in the matching cluster folders. | `OUTPUT_BASE_DIR`. |
| `g_plot_reference_kpi_comparison.py` | `EXAMPLES_BASE_DIR` and the configured reference/cluster selections. | `OUTPUT_BASE_DIR`. |

For decentralized analysis, set `INPUT_BASE_DIR` to the parent of the result
case folders. The reader requires post-processing folders named
`post_processed_dec_k_combinations_YYYY_MM_DD`. Set `POST_PROCESS_NAME` to the
specific dated folder to avoid automatic selection of the latest available
date. The naming requirement also applies to an explicitly selected folder;
an arbitrary custom name is not accepted by this reader. Keep the
`sfh_kNN_mfh_kNN` or `sfh_reference_mfh_reference` combination names and package
filenames expected by the reader.

For centralized analysis, point `INPUT_BASE_DIR` to the consolidation output
root, retaining the case, combined-cluster, temperature, and constraint/scenario
subdirectories. Point the centralized plot analysis root to the tables generated
by its corresponding calculation script. Do not interchange a raw optimization
root, a consolidated-package root, and a hypervolume-table root.

## Execution and preservation of artifacts

After configuring the required roots and cases, the calculation scripts are
invoked from this directory, for example:

```bash
python decentralized/a_calculate_delta_hypervolume_over_k.py
python centralized/a_calculate_delta_hypervolume_centralized_over_k.py
```

These are separate analysis branches, not two mandatory consecutive commands.
Select the branch matching the available upstream packages. Read the relevant
plot parser or source settings before selecting its outputs. These commands use
the source-level configuration described above.

Profile-cache preparation may require additional EV inputs beyond the supplied
no-EV optimization example. Existing caches can be used by the corresponding
KPI readers when their content and configuration match the intended analysis.
When regenerating them, use a working copy of the input tree: the cache script
writes within that tree. Redirect `OUTPUT_DIR` before regenerating reference
workbooks to preserve the XLSX files already supplied with the repository.

Keep new tables and figures separate from original results. Record the source
revision, selected upstream packages, reference combination, temperature/group
selection, and any edited configuration alongside the generated artifacts.
The normalization and reference choices belong to the analytical procedure;
changing a filesystem root alone is a storage adaptation.

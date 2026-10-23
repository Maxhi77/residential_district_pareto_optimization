# Centralized result consolidation

This stage consolidates centralized district-level optimization results from
`03_applied_energy_optimization` for downstream inspection, analysis, and
visualization. It is part of the computational research artifact accompanying
the PhD dissertation. The [parent guide](../README.md) describes its place in
the overall post-processing workflow.

The centralized workflow differs from the decentralized post-processing: each
centralized result file already represents one district-level optimization
result. Therefore, this step does not combine building-level Pareto fronts and
does not apply Pareto pruning. It loads centralized result records, extracts
valid objective values, and writes a consolidated centralized package for each
combined-cluster, temperature-level, and constraint/scenario group.

Expected input files follow this naming pattern:

```text
res_cen_t50_cmin_simple_co2_02.pkl
res_cen_t50_cmin_co2_02.pkl
```

The recommended input for post-processing is the `simple` result variant. Full
`res_cen_t..._co2_...pkl` files can be loaded as well, but they may be large.

## Usage

The original defaults refer either to a research archive, when available, or
to the optimization directory. For locally generated results, select both
roots explicitly. From this folder, after generating the centralized outputs
described in the optimization guide:

```bash
python a_post_process_centralized_results.py \
  --input-root "$(cd ../../03_applied_energy_optimization && pwd)/local_results_centralized" \
  --output-root "$PWD/local_centralized_post_processed" \
  --ueu-case processed_bds_in_DENI03403000SEC5658 \
  --result-kind simple \
  --temperature-levels 50,80
```

`--input-root` can also point directly to one `processed_bds_in...` result case;
then omit `--ueu-case` or make it match that folder. If price scenarios use
case-name suffixes, select the intended folders or use the script's
`--price-scenarios` selection. Absolute paths keep this stage independent of
the optimizer's working directory. This invocation assumes that the selected
raw result folders already exist.

The script writes one output folder per combined cluster, temperature, and
constraint/scenario group, for example:

```text
local_centralized_post_processed/
  processed_bds_in_DENI03403000SEC5658/
    combined_cluster_sfh_k06_mfh_k01/
      t50/
        cmin/
          centralized_records.pkl
          centralized_front.pkl
          centralized_package.pkl
          meta.pkl
          summary.csv
          skipped.csv
          simple_full_consistency.csv
```

`centralized_front.pkl` contains all valid centralized records in stable sorted
order. No Pareto filtering is applied in this step.

`simple_full_consistency.csv` compares the `simple` and full result files for
the same temperature, constraint, objective, factor, and result key. Rows are
written only when one variant is missing or invalid while the other one is
valid, or when both variants are present but invalid. This helps identify cases
where the optimization likely finished, but writing one of the result variants
failed.

Retain these diagnostics and metadata with each consolidated package.
`--keep-series` preserves pandas Series in the exported records; the default
omits them to reduce package size. Simple inputs can be supplemented by their
matching full files for technology detail, so retain the original paired
optimization outputs when those details are required downstream.

For further use, point plotting or centralized Pareto-set analysis to the
selected consolidation root and its case/cluster/temperature/group structure.
The filesystem root can be changed without adopting the original archive
location; filenames and record structures remain the interface between stages.

# Centralized Post-Processing

This folder post-processes centralized district-level optimization results from
`03_applied_energy_optimization`.

The centralized workflow differs from the decentralized post-processing: each
centralized result file already represents one district-level optimization
result. Therefore, this step does not combine building-level Pareto fronts and
does not apply Pareto pruning. It loads centralized result records, extracts
valid objective values, and writes a consolidated centralized package for each
combined-cluster and temperature-level case.

Expected input files follow this naming pattern:

```text
res_cen_t50_cmin_simple_co2_02.pkl
res_cen_t50_cmin_co2_02.pkl
```

The recommended input for post-processing is the `simple` result variant. Full
`res_cen_t..._co2_...pkl` files can be loaded as well, but they may be large.

## Usage

From this folder:

```bash
python a_post_process_centralized_results.py \
  --ueu-case processed_bds_in_DENI03403000SEC4580 \
  --result-kind simple \
  --temperature-levels 50,80
```

For reproducible thesis or publication runs, pass `--input-root` and
`--output-root` explicitly:

```bash
python a_post_process_centralized_results.py \
  --input-root /path/to/thermal_building_model/src/oemof/thermal_building_model/examples/03_applied_energy_optimization/processed_bds_in_DENI03403000SEC5101 \
  --output-root /path/to/centralized_post_processed \
  --result-kind simple \
  --temperature-levels 50,80
```

The script writes one output folder per combined cluster and temperature level,
for example:

```text
../04_post_processed_cen_YYYYMMDD/
  processed_bds_in_DENI03403000SEC4580/
    combined_cluster_sfh_k02_mfh_k01/
      t50/
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

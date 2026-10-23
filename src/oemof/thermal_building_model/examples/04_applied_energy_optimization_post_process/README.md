# Applied energy optimization post-processing

This directory connects the
[optimization workflow](../03_applied_energy_optimization/README.md) to the
figures and downstream analyses of the PhD research. It documents how raw
optimization records are selected, combined or consolidated, and made available
to plotting scripts. The decentralized and centralized branches consume
different kinds of optimization outputs and should be configured separately.

Several defaults refer to the research-machine archive or to selected case
folders. These are source configuration for an inspectable research workflow.
Researchers can process independently generated results by selecting their own
roots and adapting the plot configuration while retaining the expected file
structures. The commands below assume that the required optimization outputs
already exist at the selected locations.

## Decentralized workflow

1. Generate the required building-level optimization files for the selected
   case, representative counts, refurbishment, price, and EV configuration.
   Keep the corresponding cluster tables available: their representative
   identities and occurrence counts are needed for combination.
2. Run `decentralized/a_post_process_decentralized_k_combinations.py`. It loads
   building records, scales them to the requested cluster occurrences, and
   applies the combination/filtering helpers in
   `helpers/pareto_optimal_help_functions.py` to construct district candidates.
3. Inspect `summary.csv` and the per-combination `meta.pkl`, and retain them
   with the generated packages. They record the processing status and selection
   needed to interpret subsequent figures.
4. Configure `b_plot_pareto_front_dec.py` to read the intended combined package
   and generate the selected Pareto and technology figures.
5. Where the necessary reference and sensitivity results are available,
   configure `c_plot_dec_compare_extreme_tradeoff_deviations.py` for the desired
   comparisons. This is a separate analysis branch with its own path settings.

### Roots and invocation

The result root and the cluster-data root can be different. This allows the
large optimization archive to be stored independently of the original inputs.
From this directory, an example using the supplied cluster configuration and
results previously generated under `03_applied_energy_optimization/local_results`
is:

```bash
TBM_INPUT_ROOT="$(cd ../03_applied_energy_optimization && pwd)"
TBM_RESULT_ROOT="$TBM_INPUT_ROOT/local_results"
TBM_POST_NAME="post_processed_dec_k_combinations_$(date +%Y_%m_%d)"
python decentralized/a_post_process_decentralized_k_combinations.py \
  --ueu-case processed_bds_in_DENI03403000SEC5658 \
  --base-dir "$TBM_RESULT_ROOT" \
  --cluster-base-dir "$TBM_INPUT_ROOT" \
  --cluster-ueu-case processed_bds_in_DENI03403000SEC5658 \
  --k-config-path "" --sfh-k 6 --mfh-k 1 \
  --refurbishments no_refurbishment --optimization-strategies co2 \
  --serial --output-root-name "$TBM_POST_NAME" \
  --no-resume-latest-output-root
```

Replace the root variables for another location. `--ueu-case` selects result
case folders, including any price-scenario suffix; `--cluster-ueu-case` names
the folder containing the matching input representatives. `--k-config-path ""`
disables the external JSON selection and uses the explicit `--sfh-k` and
`--mfh-k` values. When using a JSON file instead, provide its actual local path.

The default `DEFAULT_DATA_BASE_DIR` is a research archive path. Set
`--base-dir` explicitly for local outputs. `--cluster-base-dir` otherwise
defaults to the same root, so supply it separately when inputs and results
are stored in different places. Relative paths are interpreted in the script's
execution context; absolute paths avoid dependence on the working directory.

The output root is created within the selected result case:

```text
<result-root>/<case>/post_processed_dec_k_combinations_YYYY_MM_DD/
  summary.csv
  sfh_k06_mfh_k01/
    building_dict.pkl
    per_building_front.pkl
    combined_front.pkl
    combined_package.pkl
    meta.pkl
```

| Artifact | Role |
| --- | --- |
| `building_dict.pkl` | Collected building records grouped by representative and refurbishment. |
| `per_building_front.pkl` | Retained candidate records for each building representative. |
| `combined_front.pkl` | Combined district candidates consumed by plotting and Pareto-set analyses. |
| `combined_package.pkl` | A three-element list containing the building dictionary, per-building fronts, and combined front. |
| `meta.pkl`, `summary.csv` | Processing configuration, counts, and status information. |

Use an explicit new output-root name for a new analysis. Without
`--no-resume-latest-output-root`, the script can select an existing dated output
root. `--force-recompute-existing` requests replacement of existing combination
outputs and should target a working copy when preserving previous results.
The downstream decentralized hypervolume reader requires the dated form
`post_processed_dec_k_combinations_YYYY_MM_DD`, including when selecting a
folder explicitly. Use that form if the output will also feed the `05_*`
analysis; direct plotting can select a combination folder explicitly.

### Plotting configuration

The principal plot scripts use source-level configuration rather than a common
command-line interface. Review the active configuration branch, because a
later assignment can replace an earlier path setting.

| Script | Settings to review before processing local results |
| --- | --- |
| `b_plot_pareto_front_dec.py` | In the `__main__` block: `ueu_list`, `old_decentralized`, `base_path`, `out_dir`, and `combined_front_input_override_by_ueu_short`. Some entries are inferred from reference-result folders and others are overridden explicitly. Select the available case and combined-front folder. |
| `c_plot_dec_compare_extreme_tradeoff_deviations.py` | The supply-mode, reference-root, sensitivity-root, post-processing-folder, and run-subdirectory constants, followed by `out_dir` in `main()`. Reference and sensitivity inputs are separate dependencies. |
| `g_plot_specific_pareto_fronts_5658.py` | Its explicit input/output directory constants and selected case. |

For an independently generated decentralized case, point the relevant
`combined_front_input_override_by_ueu_short` entry to the combination folder
containing `combined_front.pkl`, for example
`<result-root>/<case>/post_processed_dec_k_combinations_YYYY_MM_DD/sfh_k06_mfh_k01`.
Point `base_path` to the matching processed building-data root, restrict
`ueu_list` to available cases, and select a separate figure directory with
`out_dir`. Other enabled plot branches may require additional reference inputs;
review their selection settings before execution.

After configuration, the main plot script is invoked from this directory as:

```bash
python b_plot_pareto_front_dec.py
```

This command uses the selected source configuration. Merely changing an output
path does not select the correct input scenario automatically.

## Centralized workflow

`centralized/a_post_process_centralized_results.py` reads raw centralized files,
extracts valid objective records, and writes consolidated packages grouped by
case, representative combination, temperature, and constraint/scenario token.
Each raw record already represents a district model; this stage does not
combine independent building fronts or apply Pareto pruning. See the
[centralized guide](centralized/README.md) for explicit input/output arguments
and the resulting folder structure.

## Subsequent analyses and traceability

The [Pareto-set analysis directory](../05_applied_energy_pareto_set_analysis/README.md)
uses the combined and consolidated packages for cluster-count comparisons.
Its energy-KPI branch additionally uses demand/PV caches and reference building
tables. The `a_`, `b_`, and `c_` prefixes order related files; they do not replace
the input dependencies described above.

Retain the source revision, selected input archives, path settings, processing
metadata, and figure selections with each run. The `computational_time/`
scripts form an optional branch for summarizing recorded runtimes; they have
their own input/output paths and do not generate optimization results.

Generated packages, figures, and runtime tables should be preserved separately
from their input archives. Their configured storage locations support the
original research workflow, while the explicit interfaces and documented
source settings allow the framework to be reused for new result sets.

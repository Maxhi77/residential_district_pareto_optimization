# Building and district optimization workflow

This directory contains the principal optimization entry points of the research
software accompanying the PhD dissertation. The scripts expose the computational
sequence from processed building inputs to stored energy-system results. Their
configured cases support inspection of the research; the same model components
can be reused with compatible inputs and locally selected output directories.

The following commands illustrate invocation and configuration with the
environment, solver, and inputs described in the
[repository README](../../../../../README.rst).

## Entry points and component responsibilities

| Entry point | Role |
| --- | --- |
| `decentralized_supply_single_building_multiple_heat_carrier_levels.py` | Prepare individual SFH/MFH representatives and optimize building supply for selected refurbishment, EV, price, CO2, and electricity-peak cases. The optional `--combined-optimization` mode assembles a joint model. |
| `centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py` | Assemble district models with shared heat-supply infrastructure for selected SFH/MFH representative combinations, heat-grid temperatures, refurbishment scenarios, and price cases. |

`helpers/cluster_io.py` loads existing representative tables or reference
buildings. `helpers/process_cluster.py` prepares household electricity, hot-water,
space-heating, and PV inputs. The `oemof_facades/` modules construct the carriers,
grids, technology investments, storage, and demand components used by
`oemof.solph`. Pyomo and the selected external solver execute the models.

## Inputs

SFH denotes single-family housing; MFH denotes multi-family housing. A UEU
(Urban Energy Unit) is identified by its processed case folder. The supplied
clustered case has the following layout:

```text
processed_bds_in_DENI03403000SEC5658/
  sfh_cluster_k06/sfh_cluster.pkl
  mfh_cluster_k01/mfh_cluster.pkl
  <building_id>_demand_no_EV.pkl
  processed_bds_in_DENI03403000SEC5658.gpkg
```

The cluster pickles are pandas tables describing representatives. Fields read by
the preparation code include `building_id`, `tabula_year_class`,
`net_floor_area`, `roof_surface_area`, `azimuth`, `tilt`,
`number_of_residents`, `number_of_apartments`, and `buildings_in_cluster`.
Reference selections use the case GeoPackage and its `tabula_building_type`
attribute. Household profiles contain hourly columns such as `Electricity_HH1`
and `Warm Water_HH1`, with corresponding indices for additional households.
EV scenarios require additional processed profiles and household metadata.

The scripts also read TABULA parameters, Hamburg TRY2035 weather inputs, and
the economic/refurbishment modules under `input/`. Building-data acquisition,
clustering, and household-profile generation precede these entry points.

## Execution sequence

1. Resolve the requested case, representative counts, refurbishment/price
   selection, solver, and result directories.
2. Read the corresponding building attributes and household demand files.
   Calculate space-heating demand and PV profiles using the selected building
   configuration and weather data.
3. Aggregate the 8,760-hour inputs into 30 typical periods of 24 hours using
   TSAM. Carry the occurrence information into model assembly and processing.
4. Assemble the energy-system components, solve the relevant reference problem,
   and execute the configured CO2 and electricity-peak constraint sweeps.
5. Store full and reduced result dictionaries. Supply these raw results to the
   [post-processing stage](../04_applied_energy_optimization_post_process/README.md).

The temporal settings and several reduction/scenario defaults are specified
in the source. A selected outer job can comprise many optimization solves.
`--max-jobs` in the centralized script limits outer jobs rather than individual
MILPs. The two scripts have separate configuration interfaces; do not assume
that an option in one has an identical counterpart in the other.

## Selecting local paths

Some directory settings are configurable through arguments; others remain part
of the case-study source configuration. This reflects the repository's role as
an inspectable research implementation. Local users can adapt the settings
without adopting the original research-machine directory layout.

| Setting | Decentralized workflow | Centralized workflow |
| --- | --- | --- |
| Processed building and demand root | Case folders are resolved relative to the script directory in `_prepare_group_context`. To relocate them, adapt that source setting consistently with cluster discovery. | `--input-root` selects the parent of the processed case folders. |
| New optimization outputs | `--result-storage-root`; defaults to the script directory. | `--result-storage-root`; defaults to the script directory. |
| Existing outputs used for resume checks | `--result-check-root`; defaults to the selected storage root. | Completion checks use the selected result storage root. |
| Relative command-line roots | Resolved against the script directory. | Resolved against the script directory. |
| Weather and parameter files | Package-relative references in source. | Package-relative references in source. |
| Failure logs | Diagnostics are printed by the workflow. | `ERROR_DIR` names `error_logs` relative to the current working directory. |

Use absolute paths when passing outputs to another stage. The URL-shaped
strings accepted by the root-normalization helpers are converted to filesystem
paths; the helpers do not implement FTP or other remote file transfer.

### Decentralized configuration example

Execute from this directory with an appropriate Python environment and SCIP
installed. This example selects the supplied `k=6/1` inputs. It retains the
script's reduction-factor lists and therefore describes a scenario sweep.

```bash
TBM_RESULT_ROOT="$PWD/local_results"
python decentralized_supply_single_building_multiple_heat_carrier_levels.py \
  --serial --workers 1 --solver scip --solver-threads 1 \
  --ueu-cases processed_bds_in_DENI03403000SEC5658 \
  --sfh-k 6 --mfh-k 1 \
  --refurbishments no_refurbishment --price-scenarios ref --ev no_EV \
  --result-storage-root "$TBM_RESULT_ROOT" \
  --result-check-root "$TBM_RESULT_ROOT"
```

`--sfh-k` and `--mfh-k` accept comma-separated counts or `reference`, provided
the matching inputs exist. `--refurbishments`, `--price-scenarios`, and `--ev`
select the implemented cases. Names and parameter adjustments for price
scenarios are defined in `helpers/price_scenarios.py`. Review the source
configuration before selecting scenarios requiring additional inputs.

### Centralized configuration example

Execute from this directory with Gurobi installed and licensed, or select a
compatible local solver explicitly:

```bash
TBM_INPUT_ROOT="$PWD"
TBM_RESULT_ROOT="$PWD/local_results_centralized"
python centralized_supply_multiple_buildings_multiple_heat_carrier_levels.py \
  --serial --workers 1 --solver gurobi --solver-threads 1 \
  --max-jobs 1 --temps 80 --scenario-mode capex_min_only \
  --ueu-cases processed_bds_in_DENI03403000SEC5658:1146.15 \
  --sfh-k 6 --mfh-k 1 --price-scenarios ref \
  --input-root "$TBM_INPUT_ROOT" --result-storage-root "$TBM_RESULT_ROOT"
```

The value after the case name is the heat-grid length in metres; `1146.15` is
the executable's configured value for this case. Temperature, scenario mode,
worker settings, and job slicing are additional run inputs. Record them with
the generated results. This command still executes the reduction procedure
inside the selected job.

## Result layout and interpretation

Decentralized files are grouped below the chosen result root:

```text
<result-root>/<case>/sfh_cluster_k06/
  results_dec_no_refurbishment_no_EV_<building_id>_co2_09.pkl
  simple_results_dec_no_refurbishment_no_EV_<building_id>_co2_09.pkl
<result-root>/<case>/mfh_cluster_k01/
  ...
```

The factor token `09` represents 0.9; `1` represents 1.0 and `005` represents
0.05. Price scenarios can add a suffix to the case folder. Joint decentralized
runs use a combined-cluster directory.

Full records include detailed component results and the objective/constraint
metadata. Reduced records omit the full technology result tree but retain
quantities such as `co2`, `totex`, `peak`, `peak_from_grid`, and `peak_into_grid`;
they can also contain electricity-grid time series. Scenario tuples identify
individual records within a file. Records containing `None` do not represent
completed solutions. Retain both variants for downstream processing, especially
when technology details are needed for plots.

Centralized files are grouped under
`<result-root>/<case>/combined_cluster_sfh_k06_mfh_k01/centralized/`, with names
such as `res_cen_t80_cmin_co2_1.pkl` and
`res_cen_t80_cmin_simple_co2_1.pkl`. Temperature, scenario token, and reduction
factor identify the selected result group.

The input and output schemas are part of the interface between stages. Moving
the root directory is sufficient when that structure is retained; arbitrary
renaming or changes to record keys require corresponding changes in consumers.
Pickles should be loaded only from trusted sources and in a compatible software
environment.

## Using independently generated results

Keep new runs in separate result roots. Point the decentralized combiner's
`--base-dir` to the root holding the case result folders and its
`--cluster-base-dir` to the corresponding processed input root. Point the
centralized consolidator's `--input-root` to the centralized result root.
Then adapt the input/output selections of the plotting and analysis scripts as
described in their READMEs.

Record the source revision, inputs, solver/environment versions, command-line
arguments, and edited source configuration. Existing result filenames may be
used to skip completed work, so changing a configuration within an old output
directory can mix runs. Use a new directory when investigating another case or
parameterization.

The supplied `run_*` and `stop_*` shell scripts provide host-specific process
management for the research environment. They are optional operational helpers
and must be reviewed and adapted separately for another machine or cluster.

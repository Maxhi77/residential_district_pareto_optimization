Residential district Pareto optimization
========================================

``residential_district_pareto_optimization`` is the repository and project name.
Its reusable Python package is named ``oemof.thermal_building_model``; this is
the namespace used in imports and in the package installation metadata.

The project provides thermal building and energy-system modelling components,
optimization workflows, and result-processing scripts for residential buildings
and districts. It accompanies a PhD dissertation and makes its computational
procedures available for inspection and reuse.

The software combines reusable model components with scripts configured for
the research cases. Some input, result, and figure paths are specified directly
in those scripts. These settings identify the data locations expected by the
research workflow; they are not prescribed locations for subsequent studies.
Researchers can generate their own results, adapt the relevant paths, and use
the framework with compatible inputs and result structures.

.. contents::
    :depth: 2
    :local:

Purpose and scope
-----------------

The repository supports the computational traceability of the PhD research:
readers can inspect how building records and demand profiles are transformed
into energy-system models, how scenarios are executed, and how results are
prepared for analysis and visualization. The implemented workflows include
building heat-demand calculations, PV yield preparation, investment and
operation optimization, and Pareto-set analysis.

The scripts provide the executable research configuration. Reproducing a
particular output requires the corresponding input data, parameter settings,
software environment, solver, and upstream result files. The presence of a
script or a saved result file alone does not demonstrate reproduction of an
entire study.

Scientific background and model concept
---------------------------------------

Residential heat-supply planning involves trade-offs between expenditure,
emissions, and electricity-grid interaction. Building characteristics and
refurbishment states influence heat demand and the required supply temperatures,
which in turn affect technology sizing and operation. Representing every
building individually increases computational effort. The research therefore
examines how a reduced building-stock representation affects district-level
energy-system results. The accompanying dissertation [Thesis]_ provides the
full methodological background.

An Urban Energy Unit (UEU) is the district considered in an optimization study.
Its single-family housing (SFH) and multi-family housing (MFH) stocks can be
represented by preprocessed building archetypes. Each archetype represents a
specified number of original buildings; occurrence factors map its quantities
to the represented stock. The SFH and MFH cluster counts determine the
building-stock resolution. These archetype inputs are generated upstream of
the main scripts in this repository. A separate temporal reduction uses TSAM
to aggregate hourly demand and generation profiles into typical periods with
occurrence weights. Building-stock reduction and temporal aggregation are
distinct modelling steps.

The main applied workflows calculate space-heating demand and PV profiles
before assembling an energy-system model with ``oemof.solph`` [Krien2020]_.
Household electricity and hot-water profiles, building attributes, weather,
prices, and the selected refurbishment state are inputs to each solve.
Refurbishment cases are prepared as scenarios. The optimization determines
technology investments and operation within the configured capacity and
technical constraints. Electricity, fuels, and heat are connected through
generation, conversion, storage, and demand components. Discrete heat-carrier
temperature levels represent supply requirements and temperature-dependent
technology operation.

Annual total expenditure (TOTEX) is minimized while emission and electricity-
peak limits are varied through an epsilon-constraint procedure. The scripts
first determine cost-reference results and then solve successive constraint
cases. The resulting records describe trade-offs among TOTEX, emissions
(``co2``), and maximum electricity import or export power (``peak``). A solution
is non-dominated within a candidate set if no other candidate is at least as
good in every objective and strictly better in at least one. The retained
solutions form a finite Pareto approximation for the evaluated scenarios and
constraint levels.

In the default decentralized workflow, building representatives are optimized
independently. Post-processing scales and recombines their candidate solutions
to construct district-level approximations, using filtering and archive
reduction to control the number of combinations. In the centralized workflow,
the selected representatives are optimized jointly with shared heat-generation,
storage, and heat-grid infrastructure. Each centralized solution already
describes a district system; its downstream processing consolidates those
records. Comparing different SFH/MFH cluster counts then assesses how the
chosen building representation changes energy quantities and the resulting
sets of trade-offs.

Repository organization
-----------------------

The Python sources are located in ``src/oemof/thermal_building_model``:

* ``m_5RC.py`` implements a thermal building model embedded in optimization;
  the earlier operational examples illustrate this execution path.
* ``tabula/`` contains the building-typology reader and its parameter table.
* ``helpers/`` contains building and household preprocessing, PV preparation,
  cluster loading, scenario selection, and result-file utilities.
* ``oemof_facades/`` contains carriers, grid connections, demands, technology
  and refurbishment components, and reusable model-assembly functions.
* ``input/`` contains economic and refurbishment parameters, weather files,
  and profiles used by the single-building examples.
* ``examples/01_basic_examples`` and ``02_investment_optimization`` contain
  earlier operational and investment examples.
* ``examples/03_applied_energy_optimization`` contains the main decentralized
  and centralized optimization scripts and the supplied processed district case.
* ``examples/04_applied_energy_optimization_post_process`` contains result
  combination, centralized consolidation, and plotting scripts.
* ``examples/05_applied_energy_pareto_set_analysis`` contains Pareto-set
  comparisons, energy-KPI analyses, and reference workbooks.

The root directory contains ``setup.py`` for package metadata and dependency
requirements, ``environment.yml`` for a Conda environment, and
``requirements-lock.txt`` for direct dependency pins. Tests are stored in
``tests/``. The workflow scripts are used from a source checkout.

Computational workflow
----------------------

The main applied workflow has five stages:

1. Load preprocessed single-family housing (SFH) and multi-family housing (MFH)
   representatives, or reference buildings, for an Urban Energy Unit (UEU).
   Read the corresponding household demand profiles and building attributes.
2. Calculate space-heating demand and PV yield, prepare the selected
   refurbishment and price scenarios, and aggregate hourly profiles into
   representative periods.
3. Assemble the energy-system models, solve the cost-reference cases, and
   execute the configured emission and electricity-peak constraint sweeps.
4. Save full and reduced optimization result dictionaries. Combine
   decentralized building results into district candidates, or consolidate
   the centralized district results.
5. Compare the resulting sets across building-stock resolutions and generate
   figures and tables. Energy-profile caches and reference workbooks support
   a separate, partly independent KPI analysis branch.

The main applied supply-system workflows prepare thermal demand before
optimization. They should be distinguished from the earlier examples using
``m_5RC.py`` to represent thermal states inside the optimization model.

Detailed stage guides are provided in:

* `Optimization workflow <src/oemof/thermal_building_model/examples/03_applied_energy_optimization/README.md>`_
* `Post-processing and plotting <src/oemof/thermal_building_model/examples/04_applied_energy_optimization_post_process/README.md>`_
* `Centralized result consolidation <src/oemof/thermal_building_model/examples/04_applied_energy_optimization_post_process/centralized/README.md>`_
* `Pareto-set and energy-KPI analysis <src/oemof/thermal_building_model/examples/05_applied_energy_pareto_set_analysis/README.md>`_

Interpreting Pareto-set comparisons
-----------------------------------

The analysis scripts compare district-level solution sets using two
complementary indicators, following the references used in Section 4.1.4 of
the dissertation:

* **Hypervolume (HV)** measures the objective-space volume dominated by a
  solution set and bounded by a specified reference point [Bader2011]_. With
  common scaling and the same reference point, larger HV indicates a larger
  dominated volume for the minimization objectives considered here. The
  reported relative deviation from the reference is
  ``100 * (HV_reference - HV_candidate) / HV_reference``: positive values
  indicate a smaller volume, negative values a larger volume, and values
  near zero a similar volume.
* **Inverted generational distance (IGD)** averages the Euclidean distance
  from each point of a prescribed reference set to its nearest candidate
  point [Coello2004]_ [Ishibuchi2015]_. Smaller values indicate closer
  agreement with that reference set. The scripts use conventional IGD;
  its lack of Pareto compliance is discussed by Ishibuchi et al.
  [Ishibuchi2015]_. It is therefore interpreted alongside HV.

For each comparison group, the scripts normalize each objective using the
minimum and maximum over the available solution sets. Normalized HV uses the
reference point ``(1.05, 1.05, 1.05)``. IGD is exported for both unscaled and
normalized objective values; normalization places the three objectives on
comparable numerical scales. Comparisons are performed separately for
decentralized and centralized results, with centralized groups also
distinguished by temperature and constraint type where present.

The reference/reference combination supplies the unclustered numerical
reference set. It is itself a finite approximation, so these indicators
describe agreement with available computed results. Similar HV values alone
do not establish similar front geometry. Interpretation also depends on the
included scenarios, normalization range, and reference-set coverage. The
`analysis guide <src/oemof/thermal_building_model/examples/05_applied_energy_pareto_set_analysis/README.md>`_
documents the required result packages and output tables.

Environment and installation
----------------------------

``environment.yml`` specifies Python 3.12.3 and the declared scientific Python
dependencies. ``setup.py`` and ``requirements-lock.txt`` additionally identify
the required ``oemof.solph`` Git revision:
``1a33411d8bbc4363b297cefe1e08ba0ff150a633``. The model components use
investment attributes provided by that revision. An arbitrary solph release
should not be assumed to provide the same interface.

A source-based installation follows the repository's environment specification.
From the repository root:

.. code:: bash

    conda env create -f environment.yml
    conda activate thermal-building-model

For an existing Python environment, the declared pip installation sequence is:

.. code:: bash

    python -m pip install oemof.network==0.5.0
    python -m pip install -r requirements-lock.txt
    python -m pip install -e .

The separate installation of ``oemof.network`` precedes setup of the pinned
solph source. The environment files pin direct dependencies; they do not
constitute a complete lock of transitive packages, system libraries, or solvers.
Local execution also requires compatible package versions and a working MILP
solver. The dependency declarations specify the research configuration;
compatibility in a new environment must be established separately.

A Pyomo-compatible solver must be installed separately. The decentralized
entry point defaults to ``scip`` and the centralized entry point to ``gurobi``;
``--solver`` selects the local backend. Gurobi requires an appropriate license.
Record the solver version and options when reporting a run.

Research configuration and path adaptation
------------------------------------------

Configuration is distributed between command-line arguments, parameter modules,
and source-level settings. This organization exposes the choices used by the
research scripts and supports inspection of the computational procedure.
It also means that a new researcher must review the relevant script settings
before execution.

In particular:

* Both main optimizers accept ``--result-storage-root``. The decentralized
  optimizer also accepts ``--result-check-root`` for resume checks.
* The centralized optimizer accepts ``--input-root``. The decentralized
  optimizer reads processed case folders relative to its script directory.
* The post-processing scripts accept input/result roots. The decentralized
  combiner can read cluster metadata from a separate directory.
* Several plotting and Pareto/KPI scripts retain absolute research-machine
  paths or source-level input and output constants. Their stage READMEs name
  the settings that must be adapted for locally generated results.

Prefer absolute paths when passing directories between stages, because the
optimizers resolve relative roots against their script directory whereas other
scripts can resolve them against the current working directory. Retain the
expected case names, cluster subdirectories, filenames, and pickle structures
when relocating results. Different studies can use different storage locations
without changing the model equations.

Technical and economic parameters are supplied through
``input/economics/investment_components.py``,
``input/economics/investment_components_heat_grid.py``,
``input/economics/investment_infrastructure_heat_grid.py``,
``input/economics/operation_grid_economics.py``, and
``input/refurbishment/refurbishment_data.py``. Weather selection, temporal
aggregation, and some scenario defaults are configured in the executable
scripts. Changes to these parameters can affect results and should be recorded
separately from changes to storage paths.

Inputs and generated artifacts
------------------------------

The checkout includes the processed case
``processed_bds_in_DENI03403000SEC5658`` under the optimization directory,
including ``sfh_cluster_k06``, ``mfh_cluster_k01``, a case GeoPackage, and
``*_demand_no_EV.pkl`` household profiles. Matching data are required for any
other case, cluster resolution, or EV scenario selected for a run.

The optimization entry points consume already processed building, clustering,
and household inputs. They do not acquire the original building database,
create new clusterings, or execute LoadProfileGenerator. Existing weather
source notes are stored in ``input/weather_files/information.md``.

Full optimization pickles contain detailed technology and flow results;
reduced pickles retain the objective values and metadata used downstream.
Post-processing produces combined or consolidated result packages, CSV
summaries, and metadata. Plotting and analysis scripts then produce figures
and tables. The stage guides describe their directory structures.

Result paths refer to files that a researcher must generate or obtain
separately; configured archive locations do not imply that those archives are
included in this checkout. The supplied XLSX workbooks are supplementary
reference tables and do not replace missing optimization outputs.

Reusing the framework and recording a run
-----------------------------------------

For a new application, provide compatible processed inputs, select the intended
scenarios, direct outputs to a separate working directory, and point downstream
scripts to those generated outputs. The reusable facades can also be used from
new scripts with explicit component parameters. Preserve completed research
outputs when experimenting with a new configuration.

For computational traceability, retain the Git revision, environment and solver
versions, input identifiers, scenario arguments, any edited source settings,
and the output-directory mapping. Store post-processing metadata and summaries
with the results they describe. Resume checks can depend on existing filenames;
use separate result roots when changing the configuration of a study.

The documentation describes the implementation and its execution dependencies.
It is not an execution log or a claim that all dissertation outputs have been
regenerated. Retain execution records separately with each computational run.

The existing MIT license covers the software under its stated terms. Confirm
the provenance and redistribution conditions of external datasets separately;
the presence of a data file does not by itself establish publication rights.
For software citation, identify the repository and the precise commit or release
used in the research.

References
----------

.. [Thesis] Hillen, M. *Archetype-Based Model Reduction for Multi-Objective
   District Energy System Optimization: Centralized and Decentralized
   Residential Heat Supply*. Accompanying PhD dissertation, Chapters 3 and 4.
   Section 4.1.4 describes the Pareto-set comparison indicators.

.. [Krien2020] Krien, U., et al. (2020). oemof.solph—A model generator for
   linear and mixed-integer linear optimisation of energy systems.
   *Software Impacts*, 6, 100028.
   `doi:10.1016/j.simpa.2020.100028 <https://doi.org/10.1016/j.simpa.2020.100028>`_.

.. [Bader2011] Bader, J., and Zitzler, E. (2011). HypE: An Algorithm for Fast
   Hypervolume-Based Many-Objective Optimization. *Evolutionary Computation*,
   19(1), 45–76.
   `doi:10.1162/EVCO_a_00009 <https://doi.org/10.1162/EVCO_a_00009>`_.

.. [Coello2004] Coello Coello, C. A., and Reyes Sierra, M. (2004).
   A Study of the Parallelization of a Coevolutionary Multi-objective
   Evolutionary Algorithm. In *MICAI 2004: Advances in Artificial
   Intelligence*, LNCS 2972, 688–697. Springer.
   `doi:10.1007/978-3-540-24694-7_71 <https://doi.org/10.1007/978-3-540-24694-7_71>`_.

.. [Ishibuchi2015] Ishibuchi, H., Masuda, H., Tanigaki, Y., and Nojima, Y.
   (2015). Modified Distance Calculation in Generational Distance and
   Inverted Generational Distance. In *Evolutionary Multi-Criterion
   Optimization*, LNCS 9019, 110–125. Springer.
   `doi:10.1007/978-3-319-15892-1_8 <https://doi.org/10.1007/978-3-319-15892-1_8>`_.

Contact
========

Main author and contact person:

* Maximilian Hillen, RWTH Aachen University:
  ``maximilian.hillen@rwth-aachen.de``
* Maximilian Hillen, German Aerospace Center (DLR):
  ``maximilian.hillen@dlr.de``


Contributing
============

Contributions should preserve the distinction between documentation, software
maintenance, and changes to scientific configuration. Describe the purpose of
each change and record any effect on model behaviour, input interpretation, or
saved outputs. The existing test modules are available in ``tests/``; their
execution and solver requirements should be considered separately from this
documentation.

License
=======

MIT License

Copyright (c) 2019 oemof developing group

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

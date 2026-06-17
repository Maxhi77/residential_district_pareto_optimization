|badge_pypi| |badge_travis| |badge_docs| |badge_coverage| |link-latest-doi|

#############
oemof.thermal_building_model
#############

This package provides tools to model thermal building models as an extension of
oemof.solph.

.. contents::

About
=====

The aim of oemof.thermal_building_model is to create easily
for 20 european countries a building model
with three retrofit status. The energy system of the building model
can be optimized for a specific retrofit status, by using the
thermal inertia of the building and optimizing the internal air
temperature.

oemof.thermal_building_model is under active development.
Contributions are welcome.

Quickstart
==========

Install oemof.thermal_building_model by running

.. code:: bash

    pip install oemof.thermal_building_model

in your virtualenv. In your code, you can import modules like e.g.:

.. code:: python

    from oemof.thermal_building_model import m_5RC

Documentation
=============

Main executable scripts
=======================

The main execution entry points for reproducing the manuscript workflows are in
``src/oemof/thermal_building_model/examples``.

``decentralized_supply_single_building_multiple_heat_carrier_levels.py``
    Runs the decentralized building-level workflow from
    ``03_applied_energy_optimization``. It loads processed UEU cluster data,
    refurbishment options, EV settings, and price scenarios, then writes full
    and reduced pickle results for CO2 and peak-reduction sweeps. This is the
    currently maintained manuscript workflow.

Model-building facades
======================

The reusable model-building layer is located in
``src/oemof/thermal_building_model/oemof_facades``. These facades are the main
interface between the workflow scripts and ``oemof.solph``. They define the
building blocks used to assemble the optimization models, including energy
carriers and grids, demand profiles, decentralized and centralized supply
technologies, thermal storage, refurbishment options, and workflow-specific
scenario blocks.

The purpose of this layer is to generate flexible and repeatable optimization
models from the same scientific parameter basis. Workflow scripts select a UEU,
cluster resolution, refurbishment case, EV setting, price scenario, and
constraint-reduction targets; the facades then translate these settings into a
consistent ``oemof.solph`` energy system. This keeps the executable scripts
focused on orchestration while the physical, technical, economic, and emission
parameterization is applied in one reusable model-building layer.

``refurbishment/building_model.py`` contains the thermal building demand model.
The ``ThermalBuilding`` facade converts TABULA-based building information,
floor area, household and occupant data, refurbishment status, and the selected
time index into a space-heating demand component. The building model also
stores the heat-demand temperature level that determines to which heat-carrier
bus the space-heating demand is connected. In the decentralized workflow this
allows buildings with different thermal requirements to be represented in the
same model structure while preserving the distinction between domestic hot
water and space-heating temperature levels.

``infrastructure/demands.py`` provides demand facades for electricity,
domestic hot water, and space heating. Electricity and LPG-derived warm-water
profiles are read by the workflow helpers and then assigned to the
corresponding demand facades. Domestic hot water is connected to its demand
temperature, while the thermal building demand is connected to the heat-carrier
level of the selected building and refurbishment state. The heat-carrier facade
creates the required temperature-level buses, for example low-temperature
space-heating levels and higher domestic-hot-water or storage levels.

``infrastructure/carriers.py`` and ``infrastructure/grids.py`` define the
energy carriers and grid interfaces used in the models. Electricity, gas,
biogas, hydrogen, and heat carriers provide the buses through which
technologies, demands, and grid connections are linked. Grid facades apply the
operational cost and CO2 parameters from the input files and provide the
components used to account for grid imports, exports, and peak grid exchange.

``technologies`` contains the investment and operation facades for PV systems,
batteries, hot-water tanks, gas heaters, CHP units, heat pumps, and heat-grid
related components. These facades read the technology-specific investment,
fixed-cost, lifetime, efficiency, and emission parameters from the economics
and emissions input modules. The workflow therefore references the correct
parameter scripts indirectly: when a model is built, the selected component
configuration is copied, scaled to the building or cluster representative, and
connected to the appropriate electricity, gas, hydrogen, and heat-temperature
buses.

``scenario_blocks`` provides reusable model-assembly functions for recurring
workflow patterns. These blocks add carriers, grids, local demands, PV,
storages, conversion technologies, central heat carriers, solver handling, and
constraint-reduction logic. They are intended to make repeated model generation
less error-prone: each scenario can be rebuilt from the same input data and
parameter files while only the selected UEU, cluster size, technology set,
price scenario, and CO2 or peak constraint targets change.

The cost, emission, refurbishment, and technology assumptions used in the
manuscript are provided through the input parameter files listed below and are
applied by these facades when the models are created. The scientific
motivation, source assumptions, technology data, and cost data are described in
the accompanying paper; the repository files are the executable implementation
of those assumptions. For publication runs, changes in ``oemof_facades`` or the
corresponding input parameter files should therefore be treated as potentially
result-affecting scientific changes.

Reproducing the decentralized example workflow
==============================================

``decentralized_supply_single_building_multiple_heat_carrier_levels.py``
is the main entry point for the decentralized building-level workflow used in
the manuscript. It optimizes representative single-family and multi-family
buildings with decentralized heat-supply technologies, refurbishment options,
PV, batteries, hot-water storage, and electricity, gas, biogas, and hydrogen
grid connections. The script writes full and reduced pickle files for CO2 and
electricity-peak reduction sweeps.

Required inputs
---------------

A runnable case requires a processed UEU folder below
``src/oemof/thermal_building_model/examples/03_applied_energy_optimization``.
For clustered runs, the folder must contain matching SFH and MFH cluster files,
for example:

.. code:: text

    processed_bds_in_.../
      sfh_cluster_k06/sfh_cluster.pkl
      mfh_cluster_k01/mfh_cluster.pkl
      <building_id>_demand_no_EV.pkl

The cluster pickle files contain representative building rows with TABULA
building class, floor area, roof geometry, household information, and
``building_id``. The demand pickle files contain hourly household electricity
and warm-water demand columns, such as ``Electricity_HH1`` and
``Warm Water_HH1``. EV scenarios require the corresponding
``*_demand_yes_EV.pkl`` or ``*_demand_yes_EV2.pkl`` files.

For the manuscript workflow, household electricity, domestic hot-water, and EV
charging demand profiles were generated with the LoadProfileGenerator (LPG) and
then stored as processed demand pickle files. The repository includes the
processed data for Urban Energy Unit 5658 in
``processed_bds_in_DENI03403000SEC5658``. This is the SFH-dominated urban
energy unit used in the paper and can be used as the main decentralized example
case.

The workflow also uses repository-provided parameter and weather files:

* ``input/weather_files/03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv``
* ``input/economics/investment_components.py``
* ``input/economics/operation_grid_economics.py``
* ``input/emissions/co2_components.py``
* ``input/refurbishment/refurbishment_data.py``
* ``tabula/tabula_data_sorted.csv``

Environment and solver
----------------------

Install the package in editable mode and ensure that the workflow dependencies
and a Pyomo-compatible MILP solver are available:

.. code:: bash

    pip install -e .

For Conda or Mamba based environments, the publication environment can be
created from the repository root with:

.. code:: bash

    mamba env create -f environment.yml
    mamba activate thermal-building-model

The file ``environment.yml`` pins the direct workflow dependencies to exact
versions. Its ``pip`` section intentionally installs ``oemof.network==0.5.0``
before installing ``oemof.solph`` from the fixed Git commit
``1a33411d8bbc4363b297cefe1e08ba0ff150a633`` of the
``feature/custom_attributes_for_investments`` branch. This order is required
for the publication workflow. The file ``requirements-lock.txt`` mirrors these
direct pins for pip-based installations.

The default solver is ``scip``. Other Pyomo solver backends can be selected with
``--solver``, but solver versions and tolerances should be documented for
publication runs.

Minimal execution command
-------------------------

The following command runs a small reference-price, no-EV, no-refurbishment
case for the included UEU 5658 input data. It assumes that the command is
executed from
``src/oemof/thermal_building_model/examples/03_applied_energy_optimization``.

.. code:: bash

    python decentralized_supply_single_building_multiple_heat_carrier_levels.py \
      --serial \
      --workers 1 \
      --solver scip \
      --solver-threads 1 \
      --ueu-cases processed_bds_in_DENI03403000SEC5658 \
      --sfh-k 6 \
      --mfh-k 1 \
      --refurbishments no_refurbishment \
      --price-scenarios ref \
      --ev no_EV \
      --result-storage-root demo_results \
      --result-check-root demo_results

The script currently uses the default CO2 and peak-reduction factor lists from
the executable. Even a small case therefore runs several optimization problems.

Expected outputs
----------------

Results are written below the selected result root and grouped by UEU case,
building type, k-value, refurbishment case, EV setting, building id, and CO2
factor. Typical files are:

.. code:: text

    demo_results/processed_bds_in_DENI03403000SEC5658/
      sfh_cluster_k06/
        results_dec_no_refurbishment_no_EV_<building_id>_co2_<factor>.pkl
        simple_results_dec_no_refurbishment_no_EV_<building_id>_co2_<factor>.pkl
      mfh_cluster_k01/
        results_dec_no_refurbishment_no_EV_<building_id>_co2_<factor>.pkl
        simple_results_dec_no_refurbishment_no_EV_<building_id>_co2_<factor>.pkl

The reduced ``simple_results`` files contain the main quantities used for
Pareto-front post-processing: annualized total costs, CO2 emissions,
electricity-grid peak import/export, and the corresponding scenario metadata.

Post-processing
---------------

The ``a_``, ``b_``, and ``c_`` prefixes in the post-processing script names
indicate the suggested execution order of the decentralized analysis workflow:
first aggregate building-level optimization outputs, then create Pareto-front
figures, then run optional comparison plots.

Building-level result files can be combined into district-level Pareto-front
inputs with:

.. code:: bash

    python ../04_applied_energy_optimization_post_process/a_post_process_decentralized_k_combinations.py \
      --ueu-case processed_bds_in_DENI03403000SEC5658 \
      --base-dir demo_results \
      --cluster-base-dir . \
      --cluster-ueu-case processed_bds_in_DENI03403000SEC5658 \
      --sfh-k 6 \
      --mfh-k 1 \
      --refurbishments no_refurbishment \
      --optimization-strategies co2 \
      --serial \
      --output-root-name demo_post_processed

The post-processing step writes ``building_dict.pkl``,
``per_building_front.pkl``, ``combined_front.pkl``, ``combined_package.pkl``,
``meta.pkl``, and ``summary.csv``.

Publication figures for the decentralized Pareto fronts can be generated with
``../04_applied_energy_optimization_post_process/b_plot_pareto_front_dec.py``.
The plotting script reads a post-processed folder containing
``combined_front.pkl``. Before running it, set the input path in the script's
``combined_front_input_override_by_ueu_short`` configuration block to the
post-processing output folder and set ``out_dir`` to the desired figure output
directory. Then run:

.. code:: bash

    python ../04_applied_energy_optimization_post_process/b_plot_pareto_front_dec.py

The plotting step produces manuscript-style Pareto-front and technology
contribution figures from the post-processed decentralized result set.

Minimal example and full manuscript reproduction
------------------------------------------------

The minimal workflow verifies that the executable, input schema, solver setup,
and result structure are reproducible. It is not intended to reproduce all
manuscript figures.

Full manuscript reproduction requires the complete processed UEU datasets, all
selected SFH and MFH k-values, refurbishment cases, EV cases, price scenarios,
the full CO2 and peak-reduction sweeps, and the downstream post-processing and
plotting scripts. If processed building, demand, or weather data cannot be
redistributed, a synthetic or anonymized demo dataset should be provided and the
data provenance should be documented separately.

Known publication-readiness notes
---------------------------------

The decentralized workflow is research-code oriented and relies on preprocessed
pickle inputs. Before using it as a public reproducibility example, provide a
small redistributable demo dataset, document the exact data provenance and
solver version, and keep any changes to model equations, objectives,
constraints, parameter values, units, and output definitions out of the
documentation-only example.

Contact
========

Main author and contact person:

* Maximilian Hillen, RWTH Aachen University:
  ``maximilian.hillen@rwth-aachen.de``
* Maximilian Hillen, German Aerospace Center (DLR):
  ``maximilian.hillen@dlr.de``


Contributing
============

Everybody is welcome to contribute to the development of oemof.thermal. Find here the `developer
guidelines of oemof <https://oemof.readthedocs.io/en/latest/developing_oemof.html>`_.

Running Tests Locally
=====================

Run the unit test suite with:

.. code:: bash

    python -m pytest -q

Solver-backed unit tests require at least one MILP solver available to Pyomo.
The test suite checks for ``cbc``, ``glpk``, or ``highs`` and skips solver-backed
tests with an explicit reason when none is installed.

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

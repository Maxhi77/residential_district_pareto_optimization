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

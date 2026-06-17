#! /usr/bin/env python
# -*- encoding: utf-8 -*-

from glob import glob
from os.path import basename, join, splitext
from setuptools import find_packages, setup
import os


def read(fname):

    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name="oemof.thermal_building_model",
    version="0.0.1.dev",
    author="oemof developer group",
    author_email="maximilian.hillen@rwth-aachen.de",
    description=(
        "Thermal building mode for the open energy modelling framework."),
    url="https://github.com/Maxhi77/thermal-building-model",  # todo add correct adress
    long_description=read("README.rst"),
    long_description_content_type="text/x-rst",
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "oemof.network == 0.5.0",
        "oemof.solph @ git+https://github.com/oemof/oemof-solph.git@1a33411d8bbc4363b297cefe1e08ba0ff150a633",
        "matplotlib == 3.10.1",
        "numpy == 2.2.3",
        "pandas == 2.2.3",
        "pvlib == 0.10.4",
        "pyomo == 6.9.1",
        "tsam == 2.3.1",
        "geopandas == 1.1.3",
        "networkx == 3.4.2",
        "seaborn == 0.13.2",
        "openpyxl == 3.1.5",
    ],
    package_data={
        "demandlib": [join("bdew_data", "*.csv")],
    },
    extras_require={
        "dev": ["pytest", "sphinx", "sphinx_rtd_theme", "matplotlib"],
    },
)

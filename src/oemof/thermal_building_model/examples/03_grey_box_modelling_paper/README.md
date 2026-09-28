# Grey-Box Modelling Paper Examples

This folder contains the grey-box modelling examples for the branch
`grey_box_modelling`. It is the focused example folder for the grey-box paper
workflow.

## Files

- `operational_optimization_with_building_simulator.py` runs the base 5R1C
  building simulation example with repository weather and profile inputs.
- `operational_optimization.py` runs the calibrated building optimization using
  measured building data.
- `operational_optimization_linear.py` and `operational_optimization_gaussian.py`
  estimate grey-box correction parameters with different optimization
  approaches.
- `building_parameters.py` contains the building-specific parameter set used by
  the measured-data examples.
- `DWD_Station_4177_2024.epw`, `DWD_Station_4177_TRY_2015.epw`, and
  `Building-445-weather-station-2024.epw` provide weather input data used by
  the examples.

## Measurement Data

The measured Excel data set is not committed to the repository. By default,
the measured-data scripts expect it next to the scripts as:

```text
Datensatz_Musterhaus_KIT_2024_12_13.xlsx
```

Alternatively, set the environment variable `GREY_BOX_MEASUREMENT_FILE` to an
absolute path before running the scripts.

PowerShell example:

```powershell
$env:GREY_BOX_MEASUREMENT_FILE = "C:\path\to\Datensatz_Musterhaus_KIT_2024_12_13.xlsx"
python operational_optimization_linear.py
```

## Scope

The former `03_advanced_investment_optimization` examples were removed from
this branch because they are not part of the grey-box modelling workflow.

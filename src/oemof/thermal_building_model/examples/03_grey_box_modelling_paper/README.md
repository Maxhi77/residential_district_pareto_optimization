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

The measured data set is not committed to the repository. By default, the
measured-data scripts expect the 2024/2025 Experiment 3 CSV data in:

```text
C:\Users\hill_mx\Desktop\Input_kevin_paper\Experiment_2425\Experiment_2425
```

with the experiment CSV files in:

```text
Experiment 3\Exp3_weather.csv
Experiment 3\Exp3_heat_flows.csv
Experiment 3\Exp3_indoor_temperatures.csv
```

Alternatively, set `GREY_BOX_EXAMPLE_DIR` to another folder or
`GREY_BOX_MEASUREMENT_FILE` to an absolute file path before running the scripts.

PowerShell example:

```powershell
$env:GREY_BOX_EXAMPLE_DIR = "C:\path\to\Experiment_2425"
python operational_optimization_linear.py
```

The 2024/2025 Experiment 3 data are stored as separate CSV files. They can also
be loaded by setting `GREY_BOX_EXPERIMENT_CSV_DIR` to either the parent folder
or the folder containing `Exp3_weather.csv` and `Exp3_heat_flows.csv`:

```powershell
$env:GREY_BOX_EXPERIMENT_CSV_DIR = "C:\Users\hill_mx\Desktop\Input_kevin_paper\Experiment_2425\Experiment_2425"
python operational_optimization_linear.py
```

## Experiment 3 Input Logic

The CSV loader in `measurement_data.py` converts the measured Experiment 3
files to the column names expected by the grey-box scripts. The source files are
minute-resolved. The optimization scripts convert `Time` to a pandas datetime
index and then use hourly mean values.

### Weather And Solar Input

- `Exp3_weather.csv` is read from the Experiment 3 folder.
- The measured ambient temperature column `Tamb [°C]` is mapped to the model
  input column `T_amb [°C]`.
- The measured irradiation column is `Qsol [W/m2]`.
- For measured CSV input, `Qsol [W/m2]` is the active source for `solar_gains`.
- The scripts convert `Qsol [W/m2]` to transmitted solar gains in W with the
  effective window area from `building_parameters.py`:

```text
solar_gains [W]
  = Qsol [W/m2]
  * total_window_area [m2]
  * (1 - frame_area_fraction_of_window)
  * radiation_non_perpendicular_to_the_glazing
  * g_gl_n_window
```

- With `building_params_ifc`, this is:

```text
total_window_area = 39.717 m2
frame_area_fraction_of_window = 0.3
radiation_non_perpendicular_to_the_glazing = 0.9
g_gl_n_window = 0.6
effective solar gain factor = 15.013 m2
solar_gains [W] = Qsol [W/m2] * 15.013 m2
```

- This is an aggregated single-zone approximation. The measured weather file
  provides one global solar radiation signal, not direction-resolved radiation
  for north/east/south/west facades.

### Heat Input `Qdot`

- `Exp3_heat_flows.csv` is read from the Experiment 3 folder.
- B1, B2, and B3 are separate, architecturally identical buildings. R1-R5, K, B,
  and C are rooms/zones inside each building.
- `DH` means district heating. A column such as `B1_DH_Qth [W]` is the heat
  transferred from the district heating network to Building 1.
- The underfloor heating circuits are the room-level heat-flow columns, such as
  `B1_R1_Qth [W]` or `B1_K_Qth [W]`.
- The loader creates two separate heat-input quantities for each selected
  building:

```text
B1_Qdot_dh [W]
B1_Qdot_heating_circuit [W]
B2_Qdot_dh [W]
B2_Qdot_heating_circuit [W]
B3_Qdot_dh [W]
B3_Qdot_heating_circuit [W]
```

- It also creates aggregate columns over the selected buildings:

```text
Qdot_dh [W]
Qdot_heating_circuit [W]
Qdot_selected [W]
```

- By default, only `B1` is selected because the grey-box building parameters
  describe one building, not all three buildings together.
- By default, `Qdot_selected [W]` is set to `Qdot_heating_circuit [W]`.
- Use `GREY_BOX_BUILDINGS` to select one or more buildings.
- Use `GREY_BOX_QDOT_SOURCE` to choose which Qdot source is used for
  `Qdot_selected [W]`.

```powershell
$env:GREY_BOX_BUILDINGS = "B1"
$env:GREY_BOX_QDOT_SOURCE = "heating_circuit"
python operational_optimization_linear.py
```

Valid `GREY_BOX_QDOT_SOURCE` values are:

```text
heating_circuit
dh
```

For Building 1, `Qdot_dh [W]` includes:

```text
B1_DH_Qth [W]
```

For Building 1, `Qdot_heating_circuit [W]` includes:

```text
B1_B_Qth [W]
B1_C1_Qth [W]
B1_K_Qth [W]
B1_R1_Qth [W]
B1_R2_Qth [W]
B1_R3_Qth [W]
B1_R4.1_Qth [W]
B1_R4.2_Qth [W]
B1_R5.1_Qth [W]
B1_R5.2_Qth [W]
```

- If you select multiple buildings, the same logic is applied per building and
  then summed in `Qdot_dh [W]` and `Qdot_heating_circuit [W]`.
- `GREY_BOX_HEAT_FLOW_COLUMNS` remains available as a manual override for
  `Qdot_selected [W]` if an explicit custom heat-flow sum is needed.

```powershell
$env:GREY_BOX_HEAT_FLOW_COLUMNS = "B1_B_Qth [W],B1_K_Qth [W],B1_R1_Qth [W]"
python operational_optimization_linear.py
```

### Heating Setpoint `T_set`

- `Exp3_indoor_temperatures.csv` is read from the Experiment 3 folder when it is
  available.
- The single-zone heating setpoint `T_set [°C]` is created as the row-wise mean
  of selected setpoint columns.
- By default, every column ending in `_Tset [°C]` is included.
- With the current Experiment 3 file, the default `T_set` average includes:

```text
B1_B_Tset [°C]
B1_C2_Tset [°C]
B1_K_Tset [°C]
B1_R1_Tset [°C]
B1_R2_Tset [°C]
B1_R3_Tset [°C]
B1_R4_Tset [°C]
B1_R5_Tset [°C]
B2_B_Tset [°C]
B2_C2_Tset [°C]
B2_K_Tset [°C]
B2_R1_Tset [°C]
B2_R2_Tset [°C]
B2_R3_Tset [°C]
B2_R4_Tset [°C]
B2_R5_Tset [°C]
B3_B_Tset [°C]
B3_C2_Tset [°C]
B3_K_Tset [°C]
B3_R1_Tset [°C]
B3_R2_Tset [°C]
B3_R3_Tset [°C]
B3_R4_Tset [°C]
B3_R5_Tset [°C]
```

- The optimization scripts resample this minute-resolved `T_set [°C]` to hourly
  mean values and pass the resulting list to `M5RC` as `t_set_heating`.
- If `Exp3_indoor_temperatures.csv` or `T_set [°C]` is not available, the
  scripts fall back to the old constant weighted setpoint.
- To use only selected zone setpoints, set `GREY_BOX_TSET_COLUMNS`.
- Example:

```powershell
$env:GREY_BOX_TSET_COLUMNS = "B1_B_Tset [°C],B1_K_Tset [°C],B1_R1_Tset [°C]"
python operational_optimization_linear.py
```

### Internal Gains

- The Experiment 3 CSV files do not contain `P_appliance [W]` or
  `P_kitchen [W]`.
- For CSV input, both columns are created and set to `0.0`.
- The model input `internal_gains` is therefore zero for this measured CSV input.

### Time Handling

- The Experiment 3 files cover `2025-02-14 00:00:00+01:00` to
  `2025-02-16 23:59:00+01:00`.
- The loader keeps the measured timestamps and merges CSV files on `Time`.
- The optimization scripts use hourly means for `T_amb`, `Qdot`, `T_set`, and
  internal gains.

## Building Parameter Comparison

The paper and the data README describe three architecturally identical
buildings, named B1, B2, and B3. The current grey-box scripts use one
single-zone building parameter set, `building_params_ifc`, so the default input
selection is one building (`B1`) rather than the sum of all three buildings.

### Geometry

| Quantity | Paper / floor plan | Current `building_params_ifc` | Assessment |
| --- | --- | --- | --- |
| Number of buildings | B1, B2, B3 are three separate identical buildings | Model parameterizes one building | Consistent if one building is selected in `GREY_BOX_BUILDINGS` |
| Conditioned floor area | Paper: approximately 100 m2 living area | `floor_area = 100` m2 | Good match |
| Footprint | Floor plan: about 9.57 m x 7.75 m = 74.17 m2 | `a_floor = 74.71` m2 | Very good match |
| Rooms/zones | R1-R5, K, B, C; utility room neglected in the paper discussion | Single-zone aggregation | Acceptable for current single-zone model; not a multi-zone reproduction |
| Roof area | Not directly stated in the paper excerpt; floor plan is not a roof plan | `a_roof = 108` m2 | Plausible but not independently confirmed from supplied text |

### Envelope

| Quantity | Paper / floor plan | Current `building_params_ifc` | Assessment |
| --- | --- | --- | --- |
| Wall construction | Aerated concrete, 0.36 m, design U-value 0.23 W/(m2K) | `u_wall = 0.233` W/(m2K), `a_wall = 180.1254` m2 | Very good U-value match |
| Roof U-value | Paper: 0.18 W/(m2K) | `u_roof = 0.092` W/(m2K) | Current model is much more insulating at the roof than the paper value |
| Floor construction | Paper: 0.25 m reinforced concrete + 0.1 m Styrodur + 0.05 m screed | `u_floor = 0.181` W/(m2K) | Plausible, but the paper excerpt gives layers rather than a direct U-value |
| Window-to-wall ratios | Paper: north 20 %, east 3.5 %, south 35 %, west 13 % | Window areas: north 9.881 m2, east 3.206 m2, south 18.8 m2, west 7.83 m2 | Directional pattern matches qualitatively: south largest, east smallest |
| Total window area | Not explicitly stated in the paper excerpt | `a_window = 39.717` m2 | Plausible; derived from IFC parameters, not directly verified from the floor plan |
| Window U-value | Not stated in the paper excerpt | `u_window = 0.700` W/(m2K) | Cannot be confirmed from supplied paper text |

### Heating System And Measurements

| Quantity | Paper / data README | Current input handling | Assessment |
| --- | --- | --- | --- |
| Heat supply | All buildings supplied by KIT district heating network | `Qdot_dh [W]` from `*_DH_Qth [W]` | Consistent |
| Heat sinks | Ten underfloor heating loops per building | `Qdot_heating_circuit [W]` from room/loop `*_Qth [W]` excluding `*_DH_Qth [W]` | Consistent |
| Room loops | B, C1, K, R1, R2, R3 have one loop; R4 and R5 have two loops each | Same column structure is used for each building | Consistent |
| Solar radiation | Paper model uses solar radiation in W/m2 multiplied by a solar gain factor in m2 | Measured `Qsol [W/m2]` is multiplied by effective window area | Consistent at single-zone aggregation level |

Main uncertainty: the paper's MPC model is multi-zone and uses room-specific
solar gain factors and room-specific heat flows. The current example remains a
single-zone 5R1C model, so it aggregates zone setpoints, heating circuits, and
solar gains to one building-level input. This is suitable for a single-zone
grey-box comparison, but it is not a room-level reproduction of the paper's MPC
model.

## Scope

The former `03_advanced_investment_optimization` examples were removed from
this branch because they are not part of the grey-box modelling workflow.

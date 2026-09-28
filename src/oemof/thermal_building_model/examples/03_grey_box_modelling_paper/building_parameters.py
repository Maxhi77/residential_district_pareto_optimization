from oemof.thermal_building_model.tabula.tabula_reader import BuildingParameters

# Fensterbreite 0.9m
window_length =0.9
window_width=2.2
per_window_area= window_length * window_width
# Fensterhöhe? = 2.2
# Wandhöhe? = 2.39m
r_i=0.13
r_e=0.04
from oemof.thermal_building_model.tabula.tabula_reader import BuildingParameters
'''

Root Mean Squared Error: 374.9124788594862
[1.21268108 0.50000016 0.50000002 1.4999999  1.49999984 0.20000016
 0.20000002]
__finished__
Gefundene Parameter: [1.21268108 0.50000016 0.50000002 1.4999999  1.49999984 0.20000016
 0.2       ]'''
building_params_pdf = BuildingParameters(
    floor_area=100,  # floor_area_reference
    heat_transfer_coefficient_ventilation=0.51,
    total_air_change_rate=0.6,
    room_height=2.39,
    frame_area_fraction_of_window = 0.3,
    radiation_non_perpendicular_to_the_glazing = 0.9,
    a_roof={"a_roof_1": 85.62},
    u_roof={"u_roof_1": 0.9443}, #1/((0.033/100)/45*2+0.16/0.18+r_i+r_e)
    b_roof={"b_roof_1": 1},
    a_floor={"a_floor_1": 74.1675},
    u_floor={"u_floor_1": 3.3285}, #1/(0.30/2.3+r_i+r_e)
    b_floor={"b_floor_1": 0.5},
    a_wall={"a_wall_1": 41.39 * 4 + 17.37 * 2 - 2.6},
    u_wall={"u_wall_1": 0.3362}, #1/(0.365/0.133+0.015/0.25+r_i+r_e)
    b_wall={"b_wall_1": 1},
    a_door={"a_door_1": 2.6},
    u_door={"u_door_1": 1.3},
    a_window={"a_window_1": per_window_area * 22 },
    u_window={"u_window_1":1.0647}, #1/ (1/1.3+r_i+r_e)
    a_window_specific={
        "a_window_horizontal": 0,
        "a_window_east": per_window_area * 1,
        "a_window_south": per_window_area * 8,
        "a_window_west": per_window_area * 4,
        "a_window_north": per_window_area * 9,
    },
    delta_u_thermal_bridging={"delta_u_thermal_bridging": 0.05},
    g_gl_n_window={"g_gl_n_window_1": 0.6},
)

c_m = building_params_pdf.a_roof["a_roof_1"] * (0.033/100) * 7870 * 490 * 2 + \
      building_params_pdf.a_roof["a_roof_1"] * (0.16) * 55 * 1450 + \
      building_params_pdf.a_floor["a_floor_1"] * (0.3) * 2400 * 880 + \
      building_params_pdf.a_wall["a_wall_1"] * (0.365) * 485 * 1000 + \
      building_params_pdf.a_wall["a_wall_1"] * (0.015) * 1100 * 960

building_params_ifc = BuildingParameters(
    floor_area=100,  # floor_area_reference
    heat_transfer_coefficient_ventilation=0.51,
    total_air_change_rate=0.6,
    room_height=2.39,
    frame_area_fraction_of_window = 0.3,
    radiation_non_perpendicular_to_the_glazing = 0.9,
    a_roof={"a_roof_1": 108},
    u_roof={"u_roof_1": 0.09236017710236274}, #1/((0.033/100)/45*2+0.16/0.18+r_i+r_e)
    b_roof={"b_roof_1": 1},
    a_floor={"a_floor_1": 74.71},
    u_floor={"u_floor_1":  0.18086012680133057}, #1/(0.30/2.3+r_i+r_e)
    b_floor={"b_floor_1": 0.5},
    a_wall={"a_wall_1": 180.1254},
    u_wall={"u_wall_1": 0.2330702579916233}, #1/(0.365/0.133+0.015/0.25+r_i+r_e)
    b_wall={"b_wall_1": 1},
    a_door={"a_door_1": 2.6},
    u_door={"u_door_1": 1.3},
    a_window={"a_window_1": 39.717000000000006},
    u_window={"u_window_1":0.7003954385729743}, #1/ (1/1.3+r_i+r_e)
    a_window_specific={
        "a_window_horizontal": 0,
        "a_window_east": 3.206,
        "a_window_south": 18.800000000000004,
        "a_window_west": 7.83,
        "a_window_north": 9.881,
    },
    delta_u_thermal_bridging={"delta_u_thermal_bridging": 0.05},
    g_gl_n_window={"g_gl_n_window_1": 0.6},
)
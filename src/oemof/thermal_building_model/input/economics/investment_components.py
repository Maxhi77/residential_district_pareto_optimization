from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents

# Investment Components for each technology
battery_config = {
    1: InvestmentComponents(
        maximum_capacity=10*1000,
        minimum_capacity=0,
        cost_per_unit=1200 / 1000,
        cost_offset=500,
        co2_per_capacity=0.1303,
        lifetime=20,
        ),
    2:InvestmentComponents(
        maximum_capacity=100*1000,
        minimum_capacity=10*1000,
        cost_per_unit=850 / 1000,
        cost_offset=500,
        co2_per_capacity=0.1303,
        lifetime=20,
    )}
# capacity is m^3
hot_water_tank_config = {
    1: InvestmentComponents(
        maximum_capacity=1,
        minimum_capacity=0,
        cost_per_unit=2097.431,
        cost_offset=1048,
        co2_per_capacity=0.2695,
        lifetime=30,
        operational_cost_relative_to_capacity = 0.01
    ),
    2: InvestmentComponents(
        maximum_capacity=100,
        minimum_capacity=1,
        cost_per_unit=856.272931,
        cost_offset=2568,
        co2_per_capacity=0.2695,
        lifetime=30,
        operational_cost_relative_to_capacity = 0.01
    )}

air_heat_pump_config={
    1: InvestmentComponents(
        maximum_capacity=17.5*1000,
        minimum_capacity=2*1000,
        cost_per_unit=1718.81925 / 1000,
        cost_offset=20179.5394,
        lifetime=20,
        co2_per_capacity = 0.03097,
        operational_cost_relative_to_capacity= 0.025),
    2: InvestmentComponents(
        maximum_capacity=52.5*1000,
        minimum_capacity=17.5*1000,
        cost_per_unit=1106.02 / 1000,
        cost_offset=38937.93,
        lifetime=20,
        co2_per_capacity=0.03097,
        operational_cost_relative_to_capacity=0.025,
    ),
    3: InvestmentComponents(
        maximum_capacity=120 * 1000,
        minimum_capacity=52.5 * 1000,
        cost_per_unit=837.5 / 1000,
        cost_offset=58952.8628,
        lifetime=20,
        co2_per_capacity=0.03097,
        operational_cost_relative_to_capacity=0.025,
    )
}

gas_heater_config={
    1: InvestmentComponents(
        maximum_capacity=50*1000,
        minimum_capacity=2000,
        cost_per_unit=464.319 / 1000,
        cost_offset=8435.65,
        operational_cost_relative_to_capacity=0.01,
        co2_per_capacity=0.00809,
        lifetime=25)
    2: InvestmentComponents(
        maximum_capacity=500*1000,
        minimum_capacity=50*1000,
        cost_per_unit=340.51511 / 1000,
        cost_offset=16255.55965,
        operational_cost_relative_to_capacity=0.01,
        co2_per_capacity=0.00809,
        lifetime=25,
    )
}

pv_system_config = {1:
    InvestmentComponents(
    maximum_capacity=15*1000,
    cost_per_unit=716 /1000,
    cost_offset=500,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.91,
    lifetime=25,
),2:
    InvestmentComponents(
    maximum_capacity=1000*100,
    minimum_capacity=15*1000,
    cost_per_unit=603 /1000,
    cost_offset=500,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.91,
    lifetime=25,
)}


heat_grid_config = {
    1: InvestmentComponents(
        maximum_capacity=15*1000,
        minimum_capacity=5000,
        cost_per_unit=0,
        cost_offset=4000,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.02264,
        lifetime=25),
    2: InvestmentComponents(
        maximum_capacity=50*1000,
        minimum_capacity=15*1000,
        cost_per_unit=158.490 / 1000,
        cost_offset=5005,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.02264,
        lifetime=25,
    )
}

electric_boiler = {
    1: InvestmentComponents(
        maximum_capacity=10*1000,
        minimum_capacity=0,
        cost_per_unit=359.213/1000,
        cost_offset=7749,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.02264,
        lifetime=25),
    2: InvestmentComponents(
        maximum_capacity=50*1000,
        minimum_capacity=15*1000,
        cost_per_unit=525.977/1000,
        cost_offset=4826.081,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.02264,
        lifetime=25,
    )
}

chp_config = { #gilt für Bio gas und Wasserstoff
    1:InvestmentComponents(
        maximum_capacity=21.3*1000,
        minimum_capacity=1000,
        cost_per_unit=3856 / 1000,
        cost_offset=1000,
        operational_cost_relative_to_capacity=0.025,
        co2_per_capacity=0.02264,
        lifetime=15,
        ),
    2:InvestmentComponents(
        maximum_capacity=100*1000,
        minimum_capacity=21.3*1000,
        cost_per_unit=2573 / 1000,
        cost_offset=2000,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.02264,
        lifetime=15,
    )}
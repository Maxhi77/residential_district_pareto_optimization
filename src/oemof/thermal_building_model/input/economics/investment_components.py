from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents

# Investment Components for each technology
if True:

    battery_config = {
        1: InvestmentComponents(
            maximum_capacity=30*1000,
            minimum_capacity=0,
            cost_per_unit=750 / 1000,
            cost_offset=1000,
            co2_per_capacity=0.1303,
            lifetime=20,
            ),
        2:InvestmentComponents(
            maximum_capacity=100*1000,
            minimum_capacity=30*1000,
            cost_per_unit=625 / 1000,
            cost_offset=1000,
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
            maximum_capacity=30*1000,
            minimum_capacity=5*1000,
            cost_per_unit=1749.057 / 1000,
            cost_offset=19938.1,
            lifetime=20,
            co2_per_capacity = 0.03097,
            operational_cost_relative_to_capacity= 0.025),
        2: InvestmentComponents(
            maximum_capacity=100*1000,
            minimum_capacity=30*1000,
            cost_per_unit=1180.55678/ 1000,
            cost_offset=33470.024,
            lifetime=20,
            co2_per_capacity=0.03097,
            operational_cost_relative_to_capacity=0.025,
        )
    }

    gas_heater_config={
        1: InvestmentComponents(
            maximum_capacity=50*1000,
            minimum_capacity=2*1000,
            cost_per_unit=367.47 / 1000,
            cost_offset=7946.69,
            operational_cost_relative_to_capacity=0.01,
            co2_per_capacity=0.00809,
            lifetime=25),
        2: InvestmentComponents(
            maximum_capacity=100*1000,
            minimum_capacity=50*1000,
            cost_per_unit=216 / 1000,
            cost_offset=17943.575,
            operational_cost_relative_to_capacity=0.01,
            co2_per_capacity=0.00809,
            lifetime=25,
        )
    }

    pv_system_config = {1:
        InvestmentComponents(
        maximum_capacity=30*1000,
        cost_per_unit=1500 /1000,
        minimum_capacity=0,
        cost_offset=500,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.91,
        lifetime=25,
    ),2:
        InvestmentComponents(
        maximum_capacity=1000*100,

        cost_per_unit=1250 /1000,
        cost_offset=500,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.91,
        lifetime=25,
    )}


    heat_grid_config = {
        1: InvestmentComponents(
            maximum_capacity=15*1000,
            minimum_capacity=2000,
            cost_per_unit=481.534,
            cost_offset=6637.0,
            operational_cost_relative_to_capacity=0.02,
            co2_per_capacity=0.02264,
            lifetime=25),
        2: InvestmentComponents(
            maximum_capacity=100*1000,
            minimum_capacity=15*1000,
            cost_per_unit=326.153 / 1000,
            cost_offset=12350,
            operational_cost_relative_to_capacity=0.02,
            co2_per_capacity=0.02264,
            lifetime=25,
        )
    }

    electric_boiler = {
        1: InvestmentComponents(
            maximum_capacity=30*1000,
            minimum_capacity=2*1000,
            cost_per_unit=427.13/1000,
            cost_offset= 4624.244,
            operational_cost_relative_to_capacity=0.02,
            co2_per_capacity=0.02264,
            lifetime=25),

    }

    chp_config = { #gilt für Bio gas und Wasserstoff
        1:InvestmentComponents(
            maximum_capacity=30*1000,
            minimum_capacity=2*1000,
            cost_per_unit=3866 / 1000,
            cost_offset=43666.66,
            operational_cost_relative_to_capacity=0.025,
            co2_per_capacity=0.02264,
            lifetime=15,
            ),
        2:InvestmentComponents(
            maximum_capacity=100*1000,
            minimum_capacity=30*1000,
            cost_per_unit=3500 / 1000,
            cost_offset=41000,
            operational_cost_relative_to_capacity=0.02,
            co2_per_capacity=0.02264,
            lifetime=15,
        )
    }
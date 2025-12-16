from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

# Investment Components for each technology

full_and_not_linearized = True

if full_and_not_linearized:
    if False:
        battery_config = {
            1: InvestmentComponents(
                maximum_capacity=30 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=1 / PhysicalBaseUnit.factor,
                cost_per_unit=750 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                lifetime=20,
            ),
            2: InvestmentComponents(
                maximum_capacity=100 * 1000/ PhysicalBaseUnit.factor,
                minimum_capacity=30 * 1000 / PhysicalBaseUnit.factor,
                cost_per_unit=625 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                lifetime=20,
            )}
    if True:
        battery_config = {
            1: InvestmentComponents(
                maximum_capacity=70 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=0.5 / PhysicalBaseUnit.factor,
                cost_per_unit=750 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                operational_cost_relative_to_capacity=0.02,
                lifetime=20,
)}
    if False:
        hot_water_tank_config = {
            1: InvestmentComponents(
                maximum_capacity=100,
                minimum_capacity=0.2,
                cost_per_unit=856.272931,#856.272931
                cost_offset=2568,#2568
                co2_per_capacity=0.2695 * 100,
                lifetime=35,
                operational_cost_relative_to_capacity=0.01
            )}
    if False:
        hot_water_tank_config = {
            1: InvestmentComponents(
                maximum_capacity=2,
                minimum_capacity=0,
                cost_per_unit=1355.431,#
                cost_offset=1483,#
                co2_per_capacity=4.13*100,
                lifetime=30,
                operational_cost_relative_to_capacity=0.01
            ),
            2: InvestmentComponents(
                maximum_capacity=100,
                minimum_capacity=2,
                cost_per_unit=856.272931,
                cost_offset=2568,
                co2_per_capacity=3.53*100,
                lifetime=30,
                operational_cost_relative_to_capacity=0.01
            )}
    else:
        hot_water_tank_config = {
            1: InvestmentComponents(
                maximum_capacity=80,
                minimum_capacity=0,
                cost_per_unit=1105.85,#
                cost_offset=2025,#
                co2_per_capacity=4.13*100,
                lifetime=30,
                operational_cost_relative_to_capacity=0.01
            )}
    if False:
        pv_system_config = {1:
            InvestmentComponents(
                maximum_capacity=30 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=0 ,
                cost_per_unit=1500 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                operational_cost_relative_to_capacity=0.02,
                co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
                lifetime=25,
            ), 2:
            InvestmentComponents(
                maximum_capacity=1000 * 100 / PhysicalBaseUnit.factor,
                minimum_capacity=1000 * 30  / PhysicalBaseUnit.factor,
                cost_per_unit=1250 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                operational_cost_relative_to_capacity=0.02,
                co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
                lifetime=25,
            )}
    if True:
        pv_system_config = {1:
                InvestmentComponents(
                    maximum_capacity=100 * 1000 / PhysicalBaseUnit.factor,
                    minimum_capacity=0 ,
                    cost_per_unit=1500 / 1000 * PhysicalBaseUnit.factor,
                    cost_offset=1000,
                    operational_cost_relative_to_capacity=0.01,
                    co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
                    lifetime=25,
                )}
    chp_config = {  # gilt für Bio gas und Wasserstoff
        1: InvestmentComponents(
            maximum_capacity=30 * 1000/ PhysicalBaseUnit.factor,
            minimum_capacity=2 * 1000/ PhysicalBaseUnit.factor,
            cost_per_unit=3866 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=43666.66,
            operational_cost_relative_to_capacity=0.025,
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor,
            lifetime=15,
        ),
        2: InvestmentComponents(
            maximum_capacity=100 * 1000/ PhysicalBaseUnit.factor,
            minimum_capacity=30 * 1000/ PhysicalBaseUnit.factor,
            cost_per_unit=3500 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=41000,
            operational_cost_relative_to_capacity=0.025,
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor,
            lifetime=15,
        )
    }

air_heat_pump_config={
    1: InvestmentComponents(
        maximum_capacity=30*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=2*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1749.057 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=19938.1,
        lifetime=20,
        co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity= 0.025),
    2: InvestmentComponents(
        maximum_capacity=100*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=30*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1180.55678/ 1000 * PhysicalBaseUnit.factor,
        cost_offset=33470.024,
        lifetime=20,
        co2_per_capacity=0.03097 * PhysicalBaseUnit.factor*0.9,
        operational_cost_relative_to_capacity=0.025,
    )
}

gas_heater_config={
    1: InvestmentComponents(
        maximum_capacity=50*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=2*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=367.47 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=7946.69,
        operational_cost_relative_to_capacity=0.005,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=30),
    2: InvestmentComponents(
        maximum_capacity=100*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=50*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=216 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=17943.575,
        operational_cost_relative_to_capacity=0.005,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=30,
    )
}


electric_boiler = {
    1: InvestmentComponents(
        maximum_capacity=30*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=2*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=427.13/1000 * PhysicalBaseUnit.factor,
        cost_offset= 4624.244,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.02264 * PhysicalBaseUnit.factor,
        lifetime=25),

}


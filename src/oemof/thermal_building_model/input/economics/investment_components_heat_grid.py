from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

# Investment Components for each technology

full_and_not_linearized = True

if True:
    battery_config = {
        1: InvestmentComponents(
            maximum_capacity=10*1000 * 1000 / PhysicalBaseUnit.factor,
            minimum_capacity=20 * 1000 / PhysicalBaseUnit.factor,
            cost_per_unit=590 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=1000,
            co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
            lifetime=20,
        )}

    hot_water_tank_config = {
        1: InvestmentComponents(
            maximum_capacity=100,
            minimum_capacity=10,
            cost_per_unit=856.272931,#856.272931
            cost_offset=2568,#2568
            co2_per_capacity=3.53*100,
            lifetime=30,
            operational_cost_relative_to_capacity=0.01
        )}
    pv_system_config = {1:
            InvestmentComponents(
                maximum_capacity=100 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=0,
                cost_per_unit=1200 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                operational_cost_relative_to_capacity=0.02,
                co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
                lifetime=25,
            )}
    chp_config = {  # gilt für Bio gas und Wasserstoff
        1: InvestmentComponents(
            maximum_capacity=10*1000 * 1000/ PhysicalBaseUnit.factor,
            minimum_capacity=2*1000 * 1000/ PhysicalBaseUnit.factor,
            cost_per_unit=1509 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=0,
            operational_cost_relative_to_capacity=0.0093,
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor*0.7,
            lifetime=15,
        ),
        2: InvestmentComponents(
            maximum_capacity=2*1000 * 1000/ PhysicalBaseUnit.factor,
            minimum_capacity=300 * 1000/ PhysicalBaseUnit.factor,
            cost_per_unit=2153.0 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=0,
            operational_cost_relative_to_capacity=0.0209,
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor*0.8,
            lifetime=15,
        )
    }


air_heat_pump_config={
    1: InvestmentComponents(
        maximum_capacity=1.5*1000*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=200*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1512 / 1000 * PhysicalBaseUnit.factor*0.8,
        cost_offset=0,
        lifetime=25,
        co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity= 0.00025),
    2: InvestmentComponents(
        maximum_capacity=20*1000*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=1.5*1000*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=791/ 1000 * PhysicalBaseUnit.factor,
        cost_offset=0,
        lifetime=25,
        co2_per_capacity=0.03097 * PhysicalBaseUnit.factor*0.7,
        operational_cost_relative_to_capacity=0.000246,
    )
}

gas_heater_config={
    1: InvestmentComponents(
        maximum_capacity=10*1000*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=500*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=119 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=0,
        operational_cost_relative_to_capacity=0.000246,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor*0.8,
        lifetime=25),
    2: InvestmentComponents(
        maximum_capacity=500*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=50*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=75.439 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=10022.83,
        operational_cost_relative_to_capacity=0.000246,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor*0.7,
        lifetime=25,
    )
}




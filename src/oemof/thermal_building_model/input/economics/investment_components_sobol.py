from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

battery_config = {
        1: InvestmentComponents(
            maximum_capacity=100*1000 / PhysicalBaseUnit.factor,
            minimum_capacity=0 / PhysicalBaseUnit.factor,
            cost_per_unit=675 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=1000,
            co2_per_capacity=0.1303 / PhysicalBaseUnit.factor,
            lifetime=20,
            )}
hot_water_tank_config = {
    1: InvestmentComponents(
        maximum_capacity=50,
        minimum_capacity=0,
        cost_per_unit=367.51,
        cost_offset=2598,
        co2_per_capacity=0.2695,
        lifetime=36,
        operational_cost_relative_to_capacity=0.01
    )}
pv_system_config = {1:
    InvestmentComponents(
    maximum_capacity=100*1000 / PhysicalBaseUnit.factor,
    minimum_capacity=1000 / PhysicalBaseUnit.factor,
    cost_per_unit=1300 / 1000 * PhysicalBaseUnit.factor,

    cost_offset=500,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
    lifetime=25,
)}

air_heat_pump_config={
    1: InvestmentComponents(
        maximum_capacity=100*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=5*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1749.057 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=19938.1,
        lifetime=20,
        co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity= 0.025),
}

gas_heater_config={
    1: InvestmentComponents(
        maximum_capacity=100*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=2*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=367.47 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=7946.69,
        operational_cost_relative_to_capacity=0.01,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=25),

}




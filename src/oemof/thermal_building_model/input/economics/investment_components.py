from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

# Investment Components for each technology

full_and_not_linearized = True

if full_and_not_linearized:
    battery_config = {
        1: InvestmentComponents(
            maximum_capacity=70 * 1000 / PhysicalBaseUnit.factor,
            minimum_capacity=0 / PhysicalBaseUnit.factor,
            cost_per_unit=711 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=500,
            co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
            operational_cost_relative_to_capacity=0.02,
            lifetime=20,
)}

    hot_water_tank_config = {
        1: InvestmentComponents(
            maximum_capacity=80,
            minimum_capacity=0,
            cost_per_unit=1105.85,#
            cost_offset=2025,#
            co2_per_capacity=4.13*100,
            lifetime=30,
            operational_cost_relative_to_capacity=0.002
        )}

    pv_system_config = {1:
            InvestmentComponents(
                maximum_capacity=100 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=0 ,
                cost_per_unit=1200 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                operational_cost_relative_to_capacity=0.01,
                co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
                lifetime=25,
            )}

    chp_config = {  # gilt für Bio gas und Wasserstoff
        1: InvestmentComponents(
            maximum_capacity=60 * 1000/ PhysicalBaseUnit.factor,
            minimum_capacity=1 * 1000/ PhysicalBaseUnit.factor,
            cost_per_unit=2272 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=12177,
            operational_cost_relative_to_capacity=0.017,
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor,
            lifetime=15,
        )}
    air_heat_pump_config={
        1: InvestmentComponents(
            maximum_capacity=60*1000 / PhysicalBaseUnit.factor,
            minimum_capacity=1*1000 / PhysicalBaseUnit.factor,
            cost_per_unit=1769/ 1000 * PhysicalBaseUnit.factor,
            cost_offset=11000,
            lifetime=20,
            co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
            operational_cost_relative_to_capacity= 0.015)}

    gas_heater_config={
        1: InvestmentComponents(
            maximum_capacity=60*1000 / PhysicalBaseUnit.factor,
            minimum_capacity=0.5*1000 / PhysicalBaseUnit.factor,
            cost_per_unit=450 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=9200,
            operational_cost_relative_to_capacity=0.003,
            co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
            lifetime=25)}


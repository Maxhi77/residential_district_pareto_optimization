from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

battery_config = InvestmentComponents(
                maximum_capacity=70 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=1 / PhysicalBaseUnit.factor,
                cost_per_unit=700 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=1000,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                lifetime=20,
)
hot_water_tank_config = InvestmentComponents(
        maximum_capacity=40,
        minimum_capacity=1,
        cost_per_unit=856.272931,  # 856.272931
        cost_offset=2568,  # 2568
        co2_per_capacity=0.2695 * 100,
        lifetime=35,
        operational_cost_relative_to_capacity=0.01
    )
pv_system_config = InvestmentComponents(
        maximum_capacity=30 * 1000 / PhysicalBaseUnit.factor,
        minimum_capacity=0,
        cost_per_unit=1500 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=500,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
        lifetime=25,
)

air_heat_pump_config=InvestmentComponents(
        maximum_capacity=120*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=2*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1749.057 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=19938.1,
        lifetime=20,
        co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity= 0.025)


gas_heater_config=InvestmentComponents(
        maximum_capacity=120*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=2*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=367.47 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=7946.69,
        operational_cost_relative_to_capacity=0.01,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=25)






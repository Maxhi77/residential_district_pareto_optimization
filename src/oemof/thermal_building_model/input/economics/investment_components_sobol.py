from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

battery_config = InvestmentComponents(
                maximum_capacity=40 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=0.5 / PhysicalBaseUnit.factor,
                cost_per_unit=750 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=500,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                operational_cost_relative_to_capacity=0.02,
                lifetime=20,
)
hot_water_tank_config = InvestmentComponents(
                maximum_capacity=80,
                minimum_capacity=0,
                cost_per_unit=1105.85,#
                cost_offset=2025,#
                co2_per_capacity=4.13*100,
                lifetime=30,
                operational_cost_relative_to_capacity=0.01
            )
#https://www.pv-magazine.de/2024/08/06/fraunhofer-ise-stromgestehungskosten-fuer-neue-photovoltaik-freiflaechenanlagen-bei-41-bis-69-cent-pro-kilowattstunde-angekommen/?utm_source=chatgpt.com
pv_system_config = InvestmentComponents(
                    maximum_capacity=100 * 1000 / PhysicalBaseUnit.factor,
                    minimum_capacity=0 ,
                    cost_per_unit=1200 / 1000 * PhysicalBaseUnit.factor,
                    cost_offset=500,
                    operational_cost_relative_to_capacity=0.01,
                    co2_per_capacity=0.91 * PhysicalBaseUnit.factor,
                    lifetime=25,
                )

air_heat_pump_config=InvestmentComponents(
        maximum_capacity=50*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=1*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1749.057 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=19938.1,
        lifetime=20,
        co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity= 0.025)


gas_heater_config=InvestmentComponents(
        maximum_capacity=50*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=1*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=367.47 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=7946.69,
        operational_cost_relative_to_capacity=0.005,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=25)






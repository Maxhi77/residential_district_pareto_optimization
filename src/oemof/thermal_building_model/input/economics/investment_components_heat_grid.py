from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents, PhysicalBaseUnit

# Investment Components for each technology

full_and_not_linearized = True
if False:
    def create_investment_config(component_name, param_list, physical_factor=PhysicalBaseUnit.factor):
        """
        param_list: Liste von Dictionaries, z.B.
        [
            {"min":0, "max":30_000, "cost":750, "offset":1000, "co2":0.1303, "lifetime":20},
            {"min":30_000, "max":100_000, "cost":625, "offset":1000, "co2":0.1303, "lifetime":20},
        ]
        physical_factor: Faktor für Umrechnung (optional)
        """
        config = {}
        for i, p in enumerate(param_list, 1):
            config[i] = InvestmentComponents(
                maximum_capacity=p["max"] / physical_factor,
                minimum_capacity=p.get("min", 0) / physical_factor,
                cost_per_unit=p["cost"] / 1000 * physical_factor,
                cost_offset=p.get("offset", 0),
                co2_per_capacity=p.get("co2", 0) * physical_factor,
                lifetime=p.get("lifetime", 20),
                operational_cost_relative_to_capacity=p.get("op_cost", 0)
            )
        return config

    if full_and_not_linearized:
        battery_params = [
            {"min": 0, "max": 30_000, "cost": 750/ 1000, "offset": 1000, "co2": 0.1303, "lifetime": 20},
            {"min": 30_000, "max": 100_000, "cost": 625/ 1000, "offset": 1000, "co2": 0.1303, "lifetime": 20},
        ]
    else:
        battery_params = [
            {"min": 0, "max": 100_000, "cost": 675, "offset": 1000, "co2": 0.1303, "lifetime": 20},
        ]

    battery_config = create_investment_config("battery", battery_params)

if full_and_not_linearized:
    if True:
        battery_config = {
            1: InvestmentComponents(
                maximum_capacity=500 * 1000/ PhysicalBaseUnit.factor,
                minimum_capacity=50 * 1000 / PhysicalBaseUnit.factor,
                cost_per_unit=625 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=1000,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                lifetime=20,
            ),
            2: InvestmentComponents(
                maximum_capacity=10*1000 * 1000/ PhysicalBaseUnit.factor,
                minimum_capacity=550 * 1000 / PhysicalBaseUnit.factor,
                cost_per_unit=550 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=1000,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                lifetime=20,
            )}
    if False:
        battery_config = {
            1: InvestmentComponents(
                maximum_capacity=10*1000 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=50 * 1000 / PhysicalBaseUnit.factor,
                cost_per_unit=585 / 1000 * PhysicalBaseUnit.factor,
                cost_offset=1000,
                co2_per_capacity=0.1303 * PhysicalBaseUnit.factor,
                lifetime=20,
            )}

    if True:
        hot_water_tank_config = {
            1: InvestmentComponents(
                maximum_capacity=1000,
                minimum_capacity=50,
                cost_per_unit=28.04,
                cost_offset=88490,
                co2_per_capacity=3.53 * 100,
                lifetime=35,
                operational_cost_relative_to_capacity=0.01
            ),
            2: InvestmentComponents(
                maximum_capacity=10000,
                minimum_capacity=1000,
                cost_per_unit=33.74,
                cost_offset=53990,
                co2_per_capacity=2.93*100,
                lifetime=35,
                operational_cost_relative_to_capacity=0.01
            )}
    if False:
        hot_water_tank_config = {
            1: InvestmentComponents(
                maximum_capacity=10000,
                minimum_capacity=50,
                cost_per_unit=31.04,
                cost_offset=71240,
                co2_per_capacity=0.2695 * 100,
                lifetime=35,
                operational_cost_relative_to_capacity=0.01
            )}
    pv_system_config = {1:
            InvestmentComponents(
                maximum_capacity=100 * 1000 / PhysicalBaseUnit.factor,
                minimum_capacity=0 ,
                cost_per_unit=1350 / 1000 * PhysicalBaseUnit.factor,
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
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor,
            lifetime=15,
        ),
        2: InvestmentComponents(
            maximum_capacity=2*1000 * 1000/ PhysicalBaseUnit.factor,
            minimum_capacity=300 * 1000/ PhysicalBaseUnit.factor,
            cost_per_unit=2153.0 / 1000 * PhysicalBaseUnit.factor,
            cost_offset=0,
            operational_cost_relative_to_capacity=0.0209,
            co2_per_capacity=0.02264 * PhysicalBaseUnit.factor,
            lifetime=15,
        )
    }


air_heat_pump_config={
    1: InvestmentComponents(
        maximum_capacity=1.5*1000*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=200*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=1512 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=0,
        lifetime=25,
        co2_per_capacity = 0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity= 0.00025),
    2: InvestmentComponents(
        maximum_capacity=20*1000*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=1500*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=791/ 1000 * PhysicalBaseUnit.factor,
        cost_offset=0,
        lifetime=25,
        co2_per_capacity=0.03097 * PhysicalBaseUnit.factor,
        operational_cost_relative_to_capacity=0.000246,
    )
}

gas_heater_config={
    1: InvestmentComponents(
        maximum_capacity=10*1000*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=500*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=119 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=0,
        operational_cost_relative_to_capacity=0.02,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=25),
    2: InvestmentComponents(
        maximum_capacity=500*1000 / PhysicalBaseUnit.factor,
        minimum_capacity=50*1000 / PhysicalBaseUnit.factor,
        cost_per_unit=75.439 / 1000 * PhysicalBaseUnit.factor,
        cost_offset=10022.83,
        operational_cost_relative_to_capacity=0.01,
        co2_per_capacity=0.00809 * PhysicalBaseUnit.factor,
        lifetime=25,
    )
}




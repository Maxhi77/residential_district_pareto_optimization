from oemof.thermal_building_model.oemof_facades.base_component import GridComponents, PhysicalBaseUnit

# Gas Grid
gas_grid_config = GridComponents(
    working_rate=0.14 / 1000 * PhysicalBaseUnit.factor, #biogas
    revenue=0,
    price_change_factor=0.02,
    co2_per_flow=0.1282 / 1000 * PhysicalBaseUnit.factor)

# Gas Grid
hydrogen_grid_config = GridComponents(
    working_rate=0.22 / 1000 * PhysicalBaseUnit.factor, # https://www.sciencedirect.com/science/article/pii/S037877882200651X  https://www.sciencedirect.com/science/article/pii/S2211467X24001391
    revenue=0,
    price_change_factor=0.02,
    co2_per_flow=0.0315 / 1000 * PhysicalBaseUnit.factor)


# Electricity Grid
electricity_grid_config = GridComponents(
    working_rate=0.28 / 1000 * PhysicalBaseUnit.factor,
    revenue=0.0733 / 1000,
    price_change_factor=0.02,
    co2_per_flow=0.0783 / 1000 * PhysicalBaseUnit.factor)


# Heat Grid
heat_grid_config = GridComponents(
    working_rate=0.1432 / 1000 * PhysicalBaseUnit.factor,
    revenue=0.0 / 1000,
    price_change_factor=0.02,
    co2_per_flow=0.1655 / 1000 * PhysicalBaseUnit.factor)


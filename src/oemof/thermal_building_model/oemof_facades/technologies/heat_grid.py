from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, InvestmentComponents, PhysicalBaseUnit
from oemof import solph
from oemof.network import Bus
from typing import Dict, List, Optional, Tuple, Any

from oemof.thermal_building_model.input.economics.investment_infrastructure_heat_grid import (
    PMR_70,
    KMR_110,
    HOUSE_STATIONS,
    PUMP_STATIONS,
    _uniform_cost_triplet,
    _range_cost_triplet,
    _pipe_row,
    _house_station_row,
    _pump_station_row
)
from oemof.thermal_building_model.helpers.path_helper import get_project_root
import pandas as pd
import os
from dataclasses import dataclass, field
import copy
from oemof.thermal_building_model.input.economics.investment_components import pv_system_config

@dataclass
class HeatGridInvestmentCosts(BaseComponent):
    nominal_power: Optional[float] = None
    investment_component: Optional[InvestmentComponents] = None
    tsam_total_amount: Optional[float] = None
    value_list : Optional[List[float]] = None
    def get_bus(self):
        self.bus = solph.buses.Bus(label=f"b_{self.name.lower()}")
        return self.bus
    def create_source(self, outut_bus: Optional[Bus] = None):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        self.oemof_component_name = f"{self.name.lower()}_source"
        self.nominal_power=max(self.value_list)
        return solph.components.Source(
            label=self.oemof_component_name,
            outputs={
                outut_bus: solph.Flow(
                )
            }
        )
    def create_sink(self, input_bus: Optional[Bus] = None):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        self.oemof_component_name = f"{self.name.lower()}_sink"
        self.nominal_power=max(self.value_list)
        if self.tsam_total_amount is None:
            return solph.components.Sink(
                label=self.oemof_component_name ,
                inputs={
                    input_bus: solph.Flow(
                        fix=self.value_list,
                        nominal_value=self.nominal_power,
                        variable_costs=self.total_capex / sum(self.value_list),
                        custom_attributes={"co2": self.total.co2/ sum(self.value_list)}
                    )
                }
            )
        else:
            return solph.components.Sink(
                label=self.oemof_component_name,
                inputs={
                    input_bus: solph.Flow(
                        fix=self.value_list,
                        nominal_value=self.nominal_power,
                        variable_costs=self.total_capex/ self.tsam_total_amount,
                        custom_attributes={"co2": self.total_co2 / self.tsam_total_amount}
                    )
                }
            )

    def post_process(self):
        investment_cost = self.total_capex
        investment_co2 = self.total_co2
        return {"investment_cost": investment_cost,
                "investment_co2": investment_co2,
                "main_line":{"cost":self.main_line.cost_offset, "co2":self.main_line.co2_offset},
                "distribution_network": {"cost": self.distribution_network.cost_offset, "co2": self.distribution_network.co2_offset},
                "house_service_line": {"cost": self.house_service_line.cost_offset, "co2": self.house_service_line.co2_offset},
                "house_station": {"cost": self.house_station.cost_offset, "co2": self.house_station.co2_offset},
                "central_transfer_station": {"cost": self.central_transfer_station.cost_offset, "co2": self.central_transfer_station.co2_offset},
                "pump_station": {"cost": self.pump_station.cost_offset, "co2": self.pump_station.co2_offset},
                }



@dataclass
class HeatGridInvestment(HeatGridInvestmentCosts):
    name: str = "HeatGrid"
    pipe_length_in_meter: float = None
    heat_transfer_station_max_kW: Optional[List[float]] = None
    peak_load_in_kw: float = None
    inverter_losses: float = 0.05
    lifetime: int = 40
    fictional_demand: float = 0
    flow_temperature: float = 80
    total_heat_demand: Optional[float] = None
    cost_scenario: str = "avg"
    transfer_temperature_difference_k: float = 10.0
    main_line_paved_fraction: float = 1
    house_connection_paved_fraction: float = 1
    cost_scenario: str = "avg"  # "min", "avg", "max"
    def __post_init__(self):
        self.PIPE_CO2_PER_M = 276.81
        self.TRANSFER_STATION_CO2_PER_KW = 3.12886
        self.CENTRAL_TRANSFER_STATION_EUR_PER_KW = 277926 / 1000.0

        self.network_supply_temperature = self.get_network_supply_temperature(self.flow_temperature)
        pipe_lifetime = self._pipe_lifetime(self.network_supply_temperature)

        main_line_costs = self.calculate_pipe_costs(self.pipe_length_in_meter, self.flow_temperature)
        main_line_co2 = self.calculate_co2_cost_pipe(self.pipe_length_in_meter)
        self.main_line = InvestmentComponents(
            cost_offset=main_line_costs,
            lifetime=pipe_lifetime,
            co2_offset=main_line_co2,
            maximum_capacity=1,
        )

        distribution_network_costs = self.calculate_distribution_network_costs(
            self.total_heat_demand,
            self.flow_temperature,
        )
        self.distribution_network = InvestmentComponents(
            cost_offset=distribution_network_costs,
            lifetime=pipe_lifetime,
            maximum_capacity=1,
        )

        house_service_line_costs = self.calculate_service_line_costs(
            self.heat_transfer_station_max_kW,
            self.flow_temperature,
        )
        self.house_service_line = InvestmentComponents(
            cost_offset=house_service_line_costs,
            lifetime=pipe_lifetime,
            maximum_capacity=1,
        )

        house_station_costs = self.calculate_house_station(
            self.heat_transfer_station_max_kW,
            self.flow_temperature,
        )
        house_station_co2 = self.calculate_co2_cost_per_kW_transfer_station(
            self.heat_transfer_station_max_kW
        )
        self.house_station = InvestmentComponents(
            cost_offset=house_station_costs,
            lifetime=25,
            maximum_capacity=1,
            co2_offset=house_station_co2,
        )

        central_transfer_station_costs = self.calculate_central_transfer_station_costs(
            self.peak_load_in_kw
        )
        self.central_transfer_station = InvestmentComponents(
            cost_offset=central_transfer_station_costs,
            lifetime=25,
            maximum_capacity=1,
        )

        pump_station_costs = self.calculate_pump_station_costs(self.peak_load_in_kw)
        self.pump_station = InvestmentComponents(
            cost_offset=pump_station_costs,
            lifetime=40,
            maximum_capacity=1,
        )

        self.total_capex = (
                self.main_line.cost_offset
                + self.distribution_network.cost_offset
                + self.house_service_line.cost_offset
                + self.house_station.cost_offset
                + self.central_transfer_station.cost_offset
                + self.pump_station.cost_offset
        )

        self.total_co2 = (
                self._get_component_co2(self.main_line)
                + self._get_component_co2(self.distribution_network)
                + self._get_component_co2(self.house_service_line)
                + self._get_component_co2(self.house_station)
                + self._get_component_co2(self.central_transfer_station)
                + self._get_component_co2(self.pump_station)
        )

    # -------------------------------------------------------------------------
    # Validation / helpers
    # -------------------------------------------------------------------------
    def _validate_inputs(self) -> None:
        if self.cost_scenario not in {"min", "avg", "max"}:
            raise ValueError(
                f"cost_scenario must be one of 'min', 'avg', 'max', got: {self.cost_scenario}"
            )

        if not (0.0 <= self.main_line_paved_fraction <= 1.0):
            raise ValueError("main_line_paved_fraction must be between 0 and 1.")

        if not (0.0 <= self.house_connection_paved_fraction <= 1.0):
            raise ValueError("house_connection_paved_fraction must be between 0 and 1.")

    @staticmethod
    def _get_component_co2(component: Any) -> float:
        return float(getattr(component, "co2_offset", 0.0))

    def _scenario_key(self, base_key: str) -> str:
        return f"{base_key}_{self.cost_scenario}"

    def _scenario_value(self, row: Dict[str, Any], base_key: str) -> Optional[float]:
        key = self._scenario_key(base_key)
        if key in row:
            return row[key]
        return row.get(base_key)

    # -------------------------------------------------------------------------
    # Temperature handling
    # -------------------------------------------------------------------------
    def get_network_supply_temperature(self, building_supply_temperature: float) -> float:
        """
        Assumes self.flow_temperature is the building-side supply temperature.
        Example:
            building-side supply = 80°C
            network-side supply  = 90°C, if transfer_temperature_difference_k = 10 K
        """
        return building_supply_temperature + self.transfer_temperature_difference_k

    @staticmethod
    def interpolate_70_110(
            value_70: float,
            value_110: float,
            network_supply_temperature: float,
    ) -> float:
        """
        Linear interpolation / extrapolation along the straight line between
        the 70°C and 110°C support points.
        Also valid for temperatures below 70°C and above 110°C.
        """
        return value_70 + (
                (network_supply_temperature - 70.0) / (110.0 - 70.0)
        ) * (value_110 - value_70)

    # -------------------------------------------------------------------------
    # Table lookup
    # -------------------------------------------------------------------------
    @staticmethod
    def _select_row_by_capacity(
            table: Dict[int, Dict[str, Any]],
            required_capacity_kw: float,
            house_connection: bool = False,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Returns the first row whose approximate capacity limit is >= required_capacity_kw.
        For house connections, only rows with available house connection costs are allowed.
        """
        rows = sorted(table.items(), key=lambda x: x[1]["capacity_kw"])

        for nominal_size, row in rows:
            if house_connection and row.get("house_unpaved_avg") is None:
                continue
            if required_capacity_kw <= row["capacity_kw"]:
                return nominal_size, row

        if house_connection:
            raise ValueError(
                f"Required house-connection capacity {required_capacity_kw:.1f} kW "
                f"exceeds the tabulated range."
            )

        raise ValueError(
            f"Required main-line capacity {required_capacity_kw:.1f} kW "
            f"exceeds the tabulated range."
        )

    def _interpolated_pipe_value(
            self,
            required_capacity_kw: float,
            base_key: str,
            network_supply_temperature: float,
            house_connection: bool = False,
    ) -> float:
        """
        Select matching rows from PMR_70 and KMR_110 and interpolate/extrapolate
        the requested value between 70°C and 110°C.
        """
        _, row_70 = self._select_row_by_capacity(
            PMR_70,
            required_capacity_kw,
            house_connection=house_connection,
        )
        _, row_110 = self._select_row_by_capacity(
            KMR_110,
            required_capacity_kw,
            house_connection=house_connection,
        )

        value_70 = self._scenario_value(row_70, base_key)
        value_110 = self._scenario_value(row_110, base_key)

        if value_70 is None or value_110 is None:
            raise ValueError(
                f"Cannot interpolate '{base_key}' for required capacity "
                f"{required_capacity_kw:.1f} kW because one of the values is missing."
            )

        return self.interpolate_70_110(
            value_70=value_70,
            value_110=value_110,
            network_supply_temperature=network_supply_temperature,
        )

    def _pipe_lifetime(self, network_supply_temperature: float) -> float:
        """
        Extrapolated lifetime:
            70°C  -> 50 a
            110°C -> 30 a
        Hence:
            40°C -> 65 a
            50°C -> 60 a
            60°C -> 55 a
        """
        return self.interpolate_70_110(
            value_70=50.0,
            value_110=30.0,
            network_supply_temperature=network_supply_temperature,
        )

    @staticmethod
    def _weighted_excavation_cost(
            unpaved_cost: float,
            paved_cost: float,
            paved_fraction: float,
    ) -> float:
        return (1.0 - paved_fraction) * unpaved_cost + paved_fraction * paved_cost

    # -------------------------------------------------------------------------
    # Cost calculations
    # -------------------------------------------------------------------------
    def calculate_pipe_costs(self, pipe_length_in_meter: float, flow_temperature: float) -> float:
        """
        Main line costs:
            weighted excavation cost + material cost
        multiplied by pipe length.

        flow_temperature is assumed to be the building-side supply temperature.
        """
        network_supply_temperature = self.get_network_supply_temperature(flow_temperature)
        required_capacity_kw = self.peak_load_in_kw

        main_unpaved = self._interpolated_pipe_value(
            required_capacity_kw=required_capacity_kw,
            base_key="main_unpaved",
            network_supply_temperature=network_supply_temperature,
            house_connection=False,
        )
        main_paved = self._interpolated_pipe_value(
            required_capacity_kw=required_capacity_kw,
            base_key="main_paved",
            network_supply_temperature=network_supply_temperature,
            house_connection=False,
        )
        main_material = self._interpolated_pipe_value(
            required_capacity_kw=required_capacity_kw,
            base_key="main_material",
            network_supply_temperature=network_supply_temperature,
            house_connection=False,
        )

        excavation_cost_per_m = self._weighted_excavation_cost(
            unpaved_cost=main_unpaved,
            paved_cost=main_paved,
            paved_fraction=self.main_line_paved_fraction,
        )
        total_cost_per_m = excavation_cost_per_m + main_material

        return pipe_length_in_meter * total_cost_per_m

    def calculate_distribution_network_costs(
            self,
            total_heat_demand: Optional[float],
            flow_temperature: float,
    ) -> float:
        """
        Set to zero to avoid double counting.
        Network costs are already derived directly from the converted KWW tables.
        """
        return 0.0

    def calculate_service_line_costs(
            self,
            heat_transfer_station_max_kW: List[Tuple[float, int]],
            flow_temperature: float,
    ) -> float:
        """
        House/service line costs per connection from converted KWW tables.

        Each entry in heat_transfer_station_max_kW is assumed to be:
            (required_house_capacity_kw, number_of_houses)
        """
        network_supply_temperature = self.get_network_supply_temperature(flow_temperature)
        total_service_line_costs = 0.0

        for house_kw, number_of_houses in heat_transfer_station_max_kW:
            house_unpaved = self._interpolated_pipe_value(
                required_capacity_kw=house_kw,
                base_key="house_unpaved",
                network_supply_temperature=network_supply_temperature,
                house_connection=True,
            )
            house_paved = self._interpolated_pipe_value(
                required_capacity_kw=house_kw,
                base_key="house_paved",
                network_supply_temperature=network_supply_temperature,
                house_connection=True,
            )
            house_material = self._interpolated_pipe_value(
                required_capacity_kw=house_kw,
                base_key="house_material",
                network_supply_temperature=network_supply_temperature,
                house_connection=True,
            )

            excavation_cost_per_connection = self._weighted_excavation_cost(
                unpaved_cost=house_unpaved,
                paved_cost=house_paved,
                paved_fraction=self.house_connection_paved_fraction,
            )
            total_cost_per_connection = excavation_cost_per_connection + house_material

            total_service_line_costs += total_cost_per_connection * number_of_houses

        return total_service_line_costs

    def calculate_house_station(
            self,
            heat_transfer_station_max_kW: List[Tuple[float, int]],
            flow_temperature: float,
    ) -> float:
        """
        Uses HOUSE_STATIONS and the selected cost scenario (min/avg/max).
        """
        total_cost = 0.0

        for house_kw, number_of_houses in heat_transfer_station_max_kW:
            for capacity_class in sorted(HOUSE_STATIONS.keys()):
                if house_kw <= capacity_class:
                    row = HOUSE_STATIONS[capacity_class]
                    total_cost += row[f"investment_{self.cost_scenario}"] * number_of_houses
                    break
            else:
                row = HOUSE_STATIONS[max(HOUSE_STATIONS.keys())]
                total_cost += row[f"investment_{self.cost_scenario}"] * number_of_houses

        return total_cost

    def calculate_central_transfer_station_costs(self, peak_load_in_kw: float) -> float:
        """
        Fixed specific cost, currently unchanged because no min/max range
        was introduced for this component.
        """
        return self.CENTRAL_TRANSFER_STATION_EUR_PER_KW * peak_load_in_kw

    def calculate_pump_station_costs(self, peak_load_in_kw: float) -> float:
        """
        Uses PUMP_STATIONS and the selected cost scenario (min/avg/max).
        """
        if peak_load_in_kw <= PUMP_STATIONS["le_1000"]["threshold_kw"]:
            row = PUMP_STATIONS["le_1000"]
        else:
            row = PUMP_STATIONS["gt_1000"]

        return row[f"specific_investment_{self.cost_scenario}"] * peak_load_in_kw

    # -------------------------------------------------------------------------
    # CO2 calculations
    # -------------------------------------------------------------------------
    def calculate_co2_cost_per_kW_transfer_station(
            self,
            list_kW_demand_transfer_station: List[Tuple[float, int]],
    ) -> float:
        total_co2 = 0.0

        for peak_kw, number_of_houses in list_kW_demand_transfer_station:
            total_co2 += peak_kw * self.TRANSFER_STATION_CO2_PER_KW * number_of_houses

        return total_co2

    def calculate_co2_cost_pipe(self, pipe_length_in_meter: float) -> float:
        return self.PIPE_CO2_PER_M * pipe_length_in_meter

    # -------------------------------------------------------------------------
    # Grid loss
    # -------------------------------------------------------------------------
    def calculate_heat_grid_loss_for_flow_temperature(self) -> float:
        """
        Heat-grid losses as a function of network supply temperature.
        """
        transfer_station_loss_building = 0.025
        transfer_station_loss = 0.045

        support_points = {
            50: 0.045,
            60: 0.0575,
            70: 0.070,
            80: 0.085,
            90: 0.100,
        }

        temperature = self.network_supply_temperature
        temps = sorted(support_points.keys())

        if temperature <= temps[0]:
            heat_grid_loss = support_points[temps[0]]
        elif temperature >= temps[-1]:
            heat_grid_loss = support_points[temps[-1]]
        else:
            for t_low, t_high in zip(temps[:-1], temps[1:]):
                if t_low <= temperature <= t_high:
                    v_low = support_points[t_low]
                    v_high = support_points[t_high]
                    heat_grid_loss = v_low + (temperature - t_low) / (t_high - t_low) * (v_high - v_low)
                    break

        return 1.0 - (heat_grid_loss + transfer_station_loss_building + transfer_station_loss)
    if False:
        #lifetime 30 years
        network_supply_temperature = self.flow_temperature + 10 #Delta from heat exchanger heat grid and building
        main_line_costs = self.calculate_pipe_costs(self.pipe_length_in_meter,self.flow_temperature)
        main_line_co2 = self.calculate_co2_cost_pipe(self.pipe_length_in_meter)
        self.main_line = InvestmentComponents(
            cost_offset=main_line_costs,  # 2568
            lifetime=45,
            co2_offset=main_line_co2,
            maximum_capacity=1,
        )
        distribution_network_costs = self.calculate_distribution_network_costs(self.total_heat_demand, self.flow_temperature)
        self.distribution_network = InvestmentComponents(
            cost_offset=distribution_network_costs,  # 2568
            lifetime=45,
            maximum_capacity=1,
        )
        house_service_line_costs = self.calculate_service_line_costs(self.heat_transfer_station_max_kW,self.flow_temperature)
        self.house_service_line = InvestmentComponents(
            cost_offset=house_service_line_costs,  # 2568
            lifetime=35,
            maximum_capacity=1,
        )
        #life time 30 years
        house_station_costs = self.calculate_house_station(self.heat_transfer_station_max_kW, self.flow_temperature)
        house_station_co2 = self.calculate_co2_cost_per_kW_transfer_station(
            list_kW_demand_transfer_station=self.heat_transfer_station_max_kW)
        self.house_station = InvestmentComponents(
            cost_offset=house_station_costs,  # 2568
            lifetime=25,
            maximum_capacity=1,
            co2_offset=house_station_co2,
        )

        central_transfer_station_costs = self.calculate_central_transfer_station_costs(self.peak_load_in_kw)
        self.central_transfer_station = InvestmentComponents(
            cost_offset=central_transfer_station_costs,  # 2568
            lifetime=25,
            maximum_capacity=1,
        )

        pump_station_costs= self.calculate_pump_station_costs(self.peak_load_in_kw)
        self.pump_station = InvestmentComponents(
            cost_offset=pump_station_costs,  # 2568
            lifetime=40,
            maximum_capacity=1,
        )

        self.total_capex = (self.main_line.cost_offset +
                            self.distribution_network.cost_offset +
                            self.house_service_line.cost_offset +
                            self.house_station.cost_offset+
                            self.central_transfer_station.cost_offset+
                            self.pump_station.cost_offset)
        self.total_co2 = (self.main_line.co2_offset +
                            self.distribution_network.co2_offset +
                            self.house_service_line.co2_offset +
                            self.house_station.co2_offset+
                            self.central_transfer_station.co2_offset+
                            self.pump_station.co2_offset)
        def calculate_pipe_costs(self,pipe_length_in_meter,flow_temperature):
            # A Technologieatlas
            partially_paved_terrain_euro_per_meter_70=1129
            partially_paved_terrain_euro_per_meter_40=1136
            partially_paved_terrain_euro_per_meter=self.interpolate(partially_paved_terrain_euro_per_meter_40, partially_paved_terrain_euro_per_meter_70, flow_temperature)
            cost_pipes = pipe_length_in_meter * partially_paved_terrain_euro_per_meter
            return cost_pipes

        def calculate_distribution_network_costs(self,total_heat_demand,flow_temperature):
            # A Technologieatlas
            distribution_network_costs_euro_per_mwh_70=1351
            distribution_network_costs_euro_per_mwh_40=1071
            distribution_network_costs_euro_per_mwh=self.interpolate(distribution_network_costs_euro_per_mwh_40, distribution_network_costs_euro_per_mwh_70, flow_temperature)

            distribution_network_costs = distribution_network_costs_euro_per_mwh * total_heat_demand/1000
            return distribution_network_costs
        def calculate_house_station(self,heat_transfer_station_max_kW,flow_temperature):
            # From Technologieatlas 2025
            house_station_costs = 0
            #
            for house in heat_transfer_station_max_kW:
                house_kw=house[0]
                if house_kw < 15:
                    transfer_station_costs = (6570+10950) / 2
                elif house_kw < 30:
                    transfer_station_costs = (6390 + 10650)/2
                elif house_kw < 50:
                    transfer_station_costs = (8925 + 14875) / 2
                elif house_kw < 200:
                    transfer_station_costs = (17400+29000)/2
                elif house_kw < 500:
                    transfer_station_costs = (31125+51875)/2
                else:
                    transfer_station_costs = (41250+68750)/2
                house_station_costs += transfer_station_costs
            return house_station_costs
        def calculate_service_line_costs(self,heat_transfer_station_max_kW,flow_temperature):
            total_service_line_costs = 0
            for house in heat_transfer_station_max_kW:
                house_kw=house[0]
                number_of_houses=house[1]
                service_line_70 = {
                    'house_kw_5': 13897,
                    'house_kw_50': 14707,
                    'house_kw_100': 15577,
                    'house_kw_100_plus': 17221
                }

                # Define the service line values for flow_temperature = 70
                service_line_40 = {
                    'house_kw_5': 11025,
                    'house_kw_50': 11668,
                    'house_kw_100': 12358,
                    'house_kw_100_plus': 17221  # Assuming you will calculate or extrapolate it
                }

                # Function to calculate the interpolated value for a given house_kw range

                # Interpolation based on house_kw
                if house_kw < 5:
                    service_line_40_value = service_line_40['house_kw_5']
                    service_line_70_value = service_line_70['house_kw_5']
                elif house_kw < 50:
                    service_line_40_value = service_line_40['house_kw_50']
                    service_line_70_value = service_line_70['house_kw_50']
                elif house_kw < 100:
                    service_line_40_value = service_line_40['house_kw_100']
                    service_line_70_value = service_line_70['house_kw_100']
                else:
                    service_line_40_value = service_line_40['house_kw_100_plus']
                    service_line_70_value = service_line_70['house_kw_100_plus']
                service_line= self.interpolate(service_line_40_value, service_line_70_value, flow_temperature)
                total_service_line_costs=total_service_line_costs + service_line*number_of_houses
            return total_service_line_costs
        def calculate_central_transfer_station_costs(self,peak_load_in_kw):
            # A Technologieatlas
            central_transfer_station_in_euro_per_kW = 277926 / 1000
            costs_central_transfer_station = central_transfer_station_in_euro_per_kW * peak_load_in_kw
            return costs_central_transfer_station
        def calculate_pump_station_costs(self,total_heat_demand):
            # From Technologieatlas 2025
            if total_heat_demand < 1000:
                cost_pump_station_in_euro_per_kWh = (184+276)/2
            else:
                cost_pump_station_in_euro_per_kWh = (69 + 104) / 2
            costs_transfer_station = cost_pump_station_in_euro_per_kWh * total_heat_demand
            return costs_transfer_station
        def calculate_co2_cost_per_kW_transfer_station(self,list_kW_demand_transfer_station):
            # A Technologieatlas
            co2_per_kw_transfer_station = 3.12886
            total_co2 = 0
            for house in list_kW_demand_transfer_station:
                peak=house[0]
                number_of_houses=house[1]
                total_co2 = + total_co2 + peak*co2_per_kw_transfer_station*number_of_houses
            return total_co2
        def calculate_co2_cost_pipe(self,pipe_length_in_meter):
            return 276.81 * pipe_length_in_meter
        def calculate_heat_grid_loss_for_flow_temperature(self,flow_temperature):
            # A heated debate
            transfer_station_loss_building = 0.025
            transfer_station_loss=0.045
            if flow_temperature == 40:
                heat_grid_loss = 0.045
            elif flow_temperature == 50:
                heat_grid_loss = 0.0575
            elif flow_temperature == 60:
                heat_grid_loss = 0.07
            elif flow_temperature == 70:
                heat_grid_loss = 0.085
            elif flow_temperature == 80:
                heat_grid_loss = 0.10
            return 1 - (heat_grid_loss+transfer_station_loss_building+transfer_station_loss)
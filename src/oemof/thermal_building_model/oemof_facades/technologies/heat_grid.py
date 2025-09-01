from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, InvestmentComponents, PhysicalBaseUnit
from typing import Optional, List
from oemof import solph
from oemof.network import Bus
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
    total_heat_demand: float = 0
    def __post_init__(self):
        #lifetime 30 years
        main_line_costs = self.calculate_pipe_costs(self.pipe_length_in_meter,self.flow_temperature)
        main_line_co2 = self.calculate_co2_cost_pipe(self.pipe_length_in_meter)
        self.main_line = InvestmentComponents(
            cost_offset=main_line_costs,  # 2568
            lifetime=35,
            co2_offset=main_line_co2,
            maximum_capacity=1,
        )
        distribution_network_costs = self.calculate_distribution_network_costs(self.total_heat_demand, self.flow_temperature)
        self.distribution_network = InvestmentComponents(
            cost_offset=distribution_network_costs,  # 2568
            lifetime=35,
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
            lifetime=30,
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
            lifetime=20,
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

    def interpolate(self,value_40, value_70, flow_temperature):
        if flow_temperature >= 70:
            return value_70
        if flow_temperature <= 40:
            return value_40
        else:
            return value_40 + (flow_temperature - 40) / (70 - 40) * (value_70 - value_40)

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
        # A Technologieatlas
        house_station_costs = 0

        for house in heat_transfer_station_max_kW:
            house_kw=house[0]
            if house_kw < 5:
                transfer_station_costs = 4300
            elif house_kw < 10:
                transfer_station_costs = (4300+6900) / 2
            elif house_kw < 50:
                transfer_station_costs = (6900 + 17200)/2
            elif house_kw < 200:
                transfer_station_costs = (17200+30800)/2
            elif house_kw < 500:
                transfer_station_costs = (54200+30800)/2
            else:
                transfer_station_costs = (54200)
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
    def calculate_pump_station_costs(self,peak_load_in_kw):
        # A Technologieatlas
        cost_pump_station_in_euro_per_kW=251136 /1000
        costs_transfer_station = cost_pump_station_in_euro_per_kW * peak_load_in_kw
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
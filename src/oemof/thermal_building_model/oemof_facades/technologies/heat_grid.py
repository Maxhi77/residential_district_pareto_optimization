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
                        variable_costs=self.investment_component.cost_offset / sum(self.value_list),
                        custom_attributes={"co2": self.investment_component.co2_offset / sum(self.value_list)}
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
                        variable_costs=self.investment_component.cost_offset / self.tsam_total_amount,
                        custom_attributes={"co2": self.investment_component.co2_offset / self.tsam_total_amount}
                    )
                }
            )

    def post_process(self):
        investment_cost = self.investment_component.cost_offset
        investment_co2 = self.investment_component.co2_offset
        return {"investment_cost": investment_cost,
                "investment_co2": investment_co2}



@dataclass
class HeatGridInvestment(HeatGridInvestmentCosts):
    name: str = "HeatGrid"
    pipe_length_in_meter: float = None
    houses_with_transfer_station: int = None
    heat_transfer_station_max_kW: Optional[List[float]] = None
    peak_load_in_kw: float = None
    inverter_losses: float = 0.05
    lifetime: int = 40
    fictional_demand: float = 0
    def __post_init__(self):

        total_investment_costs = self.calculate_pipe_costs(self.pipe_length_in_meter)\
                                 + self.calculate_transfer_station_costs(self.houses_with_transfer_station)\
                                 + self.calculate_pump_station_costs(self.peak_load_in_kw)\
                                 + self.calculate_central_transfer_station_costs(self.peak_load_in_kw)
        total_co2_cost = self.calculate_co2_cost_pipe(self.pipe_length_in_meter)\
                        + self.calculate_co2_cost_per_kW_transfer_station(list_kW_demand_transfer_station=self.heat_transfer_station_max_kW)
        self.investment_component = InvestmentComponents(
            cost_offset=total_investment_costs,  # 2568
            co2_per_capacity=0.2695 * 100,
            lifetime=self.lifetime,
            co2_offset=total_co2_cost,
            maximum_capacity=10,
            cost_per_unit=0,
        )

        self.co2_cost = total_co2_cost
    def calculate_pipe_costs(self,pipe_length_in_meter):
        # A Technologieatlas
        partially_paved_terrain_euro_per_meter=1045
        cost_pipes = pipe_length_in_meter * partially_paved_terrain_euro_per_meter
        return cost_pipes
    def calculate_transfer_station_costs(self,houses_with_transfer_station):
        # A Technologieatlas
        cost_per_transfer_station= 9929
        transfer_station_costs = cost_per_transfer_station * houses_with_transfer_station
        return transfer_station_costs

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
        for peak in list_kW_demand_transfer_station:
            total_co2 = + total_co2 + peak*co2_per_kw_transfer_station
        return total_co2
    def calculate_co2_cost_pipe(self,pipe_length_in_meter):
        return 276.81 * pipe_length_in_meter
    def calculate_heat_grid_loss_for_flow_temperature(self,flow_temperature):
        # A heated debate
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
        return 1 - heat_grid_loss
from oemof.thermal_building_model.oemof_facades.base_component import (
    BaseComponent,
    InvestmentComponents,
    PhysicalBaseUnit,
    extract_investment_capacity_from_results,
)
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses

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
class RenewableEnergySource(BaseComponent):
    nominal_power: Optional[float] = None
    investment_component: Optional[InvestmentComponents] = None
    value_list : Optional[List[float]] = None

    def get_bus(self):
        self.bus = solph.buses.Bus(label=f"b_{self.name.lower()}")
        return self.bus
    def create_source(self, output_bus: Optional[Bus] = None):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        self.oemof_component_name = f"{self.name.lower()}_source"
        if self.investment:
            epc = self.investment_component.cost_per_unit   # Get EPC from economics model
            print("pv_system:"+str(epc))
            return solph.components.Source(
                label=self.oemof_component_name ,
                outputs={self.bus: solph.Flow(
                    fix = self.value_list,
                    nominal_value= solph.Investment(ep_costs=epc,
                                                    maximum=self.investment_component.maximum_capacity,
                                                    minimum=self.investment_component.minimum_capacity,
                                                    offset=self.investment_component.cost_offset,
                                                    lifetime=self.investment_component.lifetime,
                                                    nonconvex=True,

                                     custom_attributes={
                                         "co2": {
                                             "offset": self.investment_component.co2_offset if self.investment_component else 0.00,
                                              "linear": self.investment_component.co2_per_capacity if self.investment_component else 0.00
                                              }
                                      }
                        ),
                    )
                }
                ,

            )
        else:
            return solph.components.Source(
                label=self.oemof_component_name ,
                outputs={
                    self.bus: solph.Flow(
                        fix=self.value_list,
                        nominal_value=self.nominal_power,
                    )
                }
            )

    def create_sink(self) -> solph.components.Sink:
        """Creates a solph sink with revenue as variable cost."""
        self.name_sink = f"{self.name.lower()}_curtailment_capable"
        return solph.components.Sink(
            label=self.name_sink,
            inputs={self.bus: solph.Flow()},
        )

    def post_process(self,results,component,sink):
        capacity, invest_status = self.get_capacity(results,component)
        investment_cost = self.get_investment_cost(capacity,invest_status)
        investment_co2 = self.get_investment_co2(capacity,invest_status)
        flow_from_grid_produced = self.get_flow_from_grid(results,component)
        flow_from_grid_curtailment = self.get_flow_from_grid_curtailment(results, sink)
        flow_from_grid_used = flow_from_grid_produced - flow_from_grid_curtailment
        return {"capacity":capacity,
                "investment_cost":investment_cost,
                "investment_co2":investment_co2,
                "flow_from_grid_produced":flow_from_grid_produced,
                "flow_from_grid_curtailment": flow_from_grid_curtailment,
                "flow_from_grid_used": flow_from_grid_used,
                "sum":flow_from_grid_used.sum()}

    def get_capacity(self,results, component):
        if self.investment:
            return extract_investment_capacity_from_results(
                results=results,
                component=component,
                bus=self.bus,
            )
        else:
            return component.outputs[self.bus].nominal_capacity,0

    def get_investment_cost(self,capacity,invest_status):
        if self.investment:
            return capacity * self.investment_component.cost_per_unit + self.investment_component.cost_offset * invest_status
        else:
            return 0
    def get_investment_co2(self, capacity, invest_status):
        if self.investment:
            if self.investment_component.co2_offset > 0 and invest_status == 0 and capacity > 0:
                raise ValueError(f"Error: 'invest_status' is None/0, so NonConvex=False, but co2_offset > 0 for component {self.name}")
            else:
                invest_status = 0
            return capacity * self.investment_component.co2_per_capacity + self.investment_component.co2_offset * invest_status
        else:
            return 0
    def get_flow_from_grid(self,results,component):
        return results[component, self.bus]["sequences"]["flow"]
    def get_flow_from_grid_curtailment(self,results,component):
        return results[self.bus, component]["sequences"]["flow"]
@dataclass
class PVSystem(RenewableEnergySource):
    name: str = "PVSystem"
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(pv_system_config))
    inverter_losses = 0.05
    def __post_init__(self):
        if self.value_list is None:
            main_path = get_project_root()
            self.value_list = pd.read_csv(
                os.path.join(
                    main_path,
                    "thermal_building_model",
                    "input",
                    "sfh_example",
                    "pvwatts_hourly_1kW.csv",
                )
            )["AC System Output (W)"] / 1000 / PhysicalBaseUnit.factor

    def calculate_max_pv_size_based_area(self, area):
        #Photovoltaics Report —Fraunhofer Institute for Solar Energy Systems ISE with the support of PSE Projects GmbH, 2025
        installable_power_per_module_area_wp_per_m2 = 0.22 * 1000 / PhysicalBaseUnit.factor
        return installable_power_per_module_area_wp_per_m2 *area
    def update_maximum_investment_pv_capacity_based_on_area(self,area):
        self.investment_component.maximum_capacity=self.calculate_max_pv_size_based_area(area)

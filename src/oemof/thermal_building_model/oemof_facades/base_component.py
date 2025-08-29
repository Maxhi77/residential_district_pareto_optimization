from dataclasses import dataclass
from oemof.tools import economics
from typing import Optional

@dataclass(kw_only=True)
class PhysicalBaseUnit:
    Watts: float=1
    kiloWatts: float=1000
    factor = kiloWatts
@dataclass(kw_only=True)
class BaseComponent:
    name: str
    oemof_component_name: str = None
    investment: Optional[bool] = False

    def get_oemof_component_name(self) -> str:
        assert self.oemof_component_name is None, "Component is wrongly initialized"
        return  f"{self.name.lower()}"

@dataclass(kw_only=True)
class TimeConfiguration:
    lifetime: float
    observation_period: float = 20
    multiperiod: bool = True
@dataclass
class InvestmentComponents(TimeConfiguration):
    maximum_capacity: float
    cost_per_unit: float
    cost_offset: float = 0
    co2_per_capacity: float = 0
    co2_offset: float = 0
    operational_cost_relative_to_capacity: float = 0
    minimum_capacity: float = 0
    wacc: float = 0.03
    reference_unit_quantity: int = 1
    def __post_init__(self):
        self.cost_offset =self.calculate_epc(capex=self.cost_offset)
        capex = (
                self.cost_per_unit
                + self.cost_per_unit * self.operational_cost_relative_to_capacity * self.lifetime)
        self.cost_per_unit = self.calculate_epc(capex=capex)
        self.co2_per_capacity = self.co2_per_capacity  /  self.lifetime
        self.co2_offset = self.co2_offset  /  self.lifetime
    def calculate_epc(self,capex):
        return economics.annuity(capex=capex, n=self.observation_period, u=self.lifetime, wacc=self.wacc)
    def set_reference_unit_quantity(self, reference_unit_quantity: int):
        self.reference_unit_quantity = reference_unit_quantity
        self.cost_per_unit = self.cost_per_unit * reference_unit_quantity
        self.cost_offset = self.cost_offset * reference_unit_quantity
        self.co2_per_capacity = self.co2_per_capacity * reference_unit_quantity
        self.co2_offset = self.co2_offset * reference_unit_quantity
@dataclass
class EconomicsInvestmentRefurbishment(TimeConfiguration):
    material: str
    component: str
    cost_per_unit: float
    thermal_conductivity: float
    cost_offset: Optional[float] = None
    shgc: Optional[float] = None
    wacc: float = 0.03
    co2_per_unit: float  = 0
    wacc: float = 0.03
    cost_per_unit_exponent :float = 1
    reference_unit_quantity: int = 1
    # Weighted Average Cost of Capital (default 3%)
    def calculate_epc(self, investment) -> float:
        """Calculates Equivalent Annual Cost (EPC) using annuity formula."""
        capex = (
                investment
                 # ✅ Correct check
        )
        return economics.annuity(capex=capex, n=self.observation_period, u=self.lifetime, wacc=self.wacc)

@dataclass(kw_only=True)
@dataclass
class GridComponents:
    working_rate: float
    revenue: float
    price_change_factor: float
    co2_per_flow: float









from dataclasses import dataclass
from oemof.tools import economics
from typing import Any, Optional
from oemof import solph

OBSERVATION_PERIOD = 20
INTEREST_RATE =0.03

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
    """Define component lifetime and economic observation period in years.

    ``lifetime`` supplies the component lifetime to the annuity calculation and
    the divisor for annual investment-associated emissions. The economic
    observation period defaults to ``OBSERVATION_PERIOD`` (20 years).
    """

    lifetime: float
    observation_period: float = OBSERVATION_PERIOD
    # Kept for backward compatibility; capacity extraction is auto-detected
    # from result structure and does not require manual toggling anymore.
    multiperiod: Optional[bool] = None


def _as_float(value: Any) -> float:
    """Convert scalar/pandas-like objects to float."""
    if hasattr(value, "sum"):
        value = value.sum()
    return float(value)


def extract_investment_capacity_from_results(
    results: dict,
    component: Any,
    bus: Any,
) -> tuple[float, float]:
    """Return `(capacity, invest_status)` for both single- and multi-period results.

    This function auto-detects whether invest values live in `period_scalars`
    or `scalars`, removing the need for manual multiperiod flags in scripts.
    """
    result_key = (component, bus)
    node_result = results.get(result_key)
    if node_result is not None:
        period_scalars = node_result.get("period_scalars")
        if period_scalars is not None and "invest" in period_scalars:
            capacity = _as_float(period_scalars["invest"])
            if "invest_status" in period_scalars:
                invest_status = _as_float(period_scalars["invest_status"])
            else:
                invest_status = 1.0 if capacity > 0 else 0.0
            return capacity, invest_status

        scalars = node_result.get("scalars")
        if scalars is not None and "invest" in scalars:
            capacity = _as_float(scalars["invest"])
            if "invest_status" in scalars:
                invest_status = _as_float(scalars["invest_status"])
            else:
                invest_status = 1.0 if capacity > 0 else 0.0
            return capacity, invest_status

    # Fallback via node-view for compatibility with older/newer result layouts.
    node_view = solph.views.node(results, bus)
    scalars = node_view.get("scalars")
    scalar_invest_key = ((component, bus), "invest")
    scalar_status_key = ((component, bus), "invest_status")
    if scalars is not None and scalar_invest_key in scalars:
        capacity = _as_float(scalars[scalar_invest_key])
        invest_status = _as_float(scalars.get(scalar_status_key, 1.0 if capacity > 0 else 0.0))
        return capacity, invest_status

    period_scalars = node_view.get("period_scalars")
    if period_scalars is not None and scalar_invest_key in period_scalars:
        capacity = _as_float(period_scalars[scalar_invest_key])
        invest_status = _as_float(
            period_scalars.get(scalar_status_key, 1.0 if capacity > 0 else 0.0)
        )
        return capacity, invest_status

    raise KeyError(
        f"Could not extract invest information for component={component} and bus={bus}."
    )


@dataclass
class InvestmentComponents(TimeConfiguration):
    """Prepare annual cost and emission coefficients for technology investment.

    Constructor inputs ``cost_per_unit`` and ``cost_offset`` describe initial
    capacity-specific and fixed investment costs. Capacity bounds and unit
    costs must use the capacity unit of the consuming component. Any conversion
    through ``PhysicalBaseUnit.factor`` is performed in the parameter modules,
    rather than by this class.

    Initialization replaces both cost fields with equivalent annual costs.
    For the capacity-specific term, the initial cost is first increased by
    ``cost_per_unit * operational_cost_relative_to_capacity * lifetime``.
    The relative operating-cost parameter therefore expresses an annual
    fraction of the initial unit investment cost. The fixed offset is
    annualized separately. ``wacc`` is a decimal discount rate, with the
    default ``INTEREST_RATE`` of 0.03 representing 3 percent.

    The input fields ``co2_per_capacity`` and ``co2_offset`` represent
    investment-associated emission quantities in the configured emission unit.
    Initialization divides them by ``lifetime`` to obtain annual quantities;
    it does not discount these quantities.

    Construction stores ``reference_unit_quantity`` without applying a
    multiplier. Call ``set_reference_unit_quantity`` to scale the annual
    coefficients to the number of buildings represented by an archetype.
    Capacity bounds remain expressed at the representative-component level.
    """

    maximum_capacity: float
    cost_per_unit: float = 0
    cost_offset: float = 0
    co2_per_capacity: float = 0
    co2_offset: float = 0
    operational_cost_relative_to_capacity: float = 0
    minimum_capacity: float = 0
    wacc: float = INTEREST_RATE
    reference_unit_quantity: int = 1
    def __post_init__(self):
        """Convert the supplied cost and emission fields in place.

        Monetary inputs are annualized with the configured observation period,
        component lifetime, and discount rate. Emission inputs are allocated
        uniformly over the component lifetime. This step does not apply
        representative-building scaling.
        """
        self.cost_offset =self.calculate_epc(capex=self.cost_offset)
        capex = (
                self.cost_per_unit
                + self.cost_per_unit * self.operational_cost_relative_to_capacity * self.lifetime)
        self.cost_per_unit = self.calculate_epc(capex=capex)
        self.co2_per_capacity = self.co2_per_capacity  /  self.lifetime
        self.co2_offset = self.co2_offset  /  self.lifetime
    def calculate_epc(self,capex):
        """Return equivalent annual cost for an unannualized monetary input.

        Delegate to ``economics.annuity`` with ``n=observation_period``,
        ``u=lifetime``, and the decimal rate ``wacc``. The result retains the
        input's capacity basis; representative scaling is a separate step.
        """
        return economics.annuity(capex=capex, n=self.observation_period, u=self.lifetime, wacc=self.wacc)
    def set_reference_unit_quantity(self, reference_unit_quantity: int):
        """Multiply current annual coefficients by a representative count.

        Update the count and multiply ``cost_per_unit``, ``cost_offset``,
        ``co2_per_capacity``, and ``co2_offset`` in place. Minimum and maximum
        capacities are unchanged. Repeated calls multiply the already scaled
        coefficients again; they do not rebase them from the previous count.
        Start from an unscaled configuration, or a copy of it, when selecting
        a new representative count.
        """
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
class GridComponents:
    working_rate: float
    revenue: float
    price_change_factor: float
    co2_per_flow: float
    interest: float = INTEREST_RATE
    observation_period: float = OBSERVATION_PERIOD
    def discounted_average(
        self,
    ) -> "GridComponents":
        """
        Returns a new GridComponents instance where the working_rate
        is replaced by a discounted-equivalent constant average price.

        The undiscounted sum over `years` equals the discounted sum
        of the original working_rate.
        """
        r = self.interest
        if self.observation_period <= 0:
            return self

        discount_sum = sum(
            1.0 / (1.0 + r) ** t
            for t in range(1, self.observation_period + 1)
        )

        p_eq = self.working_rate * discount_sum / self.observation_period

        return GridComponents(
            working_rate=p_eq,
            revenue=self.revenue,
            price_change_factor=0.0,  # growth absorbed
            co2_per_flow=self.co2_per_flow,
        )









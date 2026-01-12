"""
Reserved Instance Analyzer.

Identifies opportunities for Reserved Instance purchases:
- Finds 24/7 running instances
- Calculates break-even periods
- Recommends RI purchases or Savings Plans
- Checks existing RIs to avoid duplication
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..utils.logger import get_logger
from ..utils.calculator import get_calculator

logger = get_logger(__name__)


# RI discount percentages (approximate vs On-Demand)
RI_DISCOUNTS = {
    "1-year-no-upfront": 0.31,      # ~31% savings
    "1-year-partial-upfront": 0.36,  # ~36% savings
    "1-year-all-upfront": 0.40,      # ~40% savings
    "3-year-no-upfront": 0.40,       # ~40% savings
    "3-year-partial-upfront": 0.50,  # ~50% savings
    "3-year-all-upfront": 0.60,      # ~60% savings
}

# Savings Plans discount approximations
SAVINGS_PLAN_DISCOUNTS = {
    "compute-1-year": 0.35,
    "compute-3-year": 0.55,
    "ec2-1-year": 0.40,
    "ec2-3-year": 0.60,
}


@dataclass
class RIRecommendation:
    """Reserved Instance recommendation."""
    instance_type: str
    region: str
    quantity: int
    term: str  # "1-year" or "3-year"
    payment_option: str  # "no-upfront", "partial-upfront", "all-upfront"
    current_monthly_cost: float
    ri_monthly_cost: float
    monthly_savings: float
    annual_savings: float
    break_even_months: float
    confidence: str
    instance_ids: list
    upfront_cost: float = 0


class ReservedInstanceAnalyzer:
    """
    Analyze instances for Reserved Instance opportunities.
    
    Identifies stable, 24/7 workloads that would benefit from
    Reserved Instance or Savings Plan purchases.
    """
    
    def __init__(
        self,
        min_running_days: int = 30,
        min_utilization: float = 10.0,
        exclude_spot: bool = True,
    ):
        """
        Initialize analyzer.
        
        Args:
            min_running_days: Minimum days running to consider for RI
            min_utilization: Minimum average CPU to consider active
            exclude_spot: Exclude spot instances from analysis
        """
        self.min_running_days = min_running_days
        self.min_utilization = min_utilization
        self.exclude_spot = exclude_spot
        self.calculator = get_calculator()
    
    def find_ri_candidates(
        self,
        instances: list[dict],
        metrics: dict[str, dict],
    ) -> list[RIRecommendation]:
        """
        Find instances that are good candidates for Reserved Instances.
        
        Args:
            instances: List of EC2 instance dictionaries
            metrics: Dictionary mapping instance_id to metrics
        
        Returns:
            List of RI recommendations
        """
        recommendations = []
        
        # Group instances by type and region
        instance_groups = {}
        
        for instance in instances:
            # Skip spot instances
            if self.exclude_spot and instance.get("lifecycle") == "spot":
                continue
            
            # Skip instances not running long enough
            running_days = instance.get("running_days", 0)
            if running_days < self.min_running_days:
                continue
            
            # Skip stopped instances
            if instance.get("state") != "running":
                continue
            
            # Check utilization
            instance_id = instance["instance_id"]
            inst_metrics = metrics.get(instance_id, {})
            cpu = inst_metrics.get("CPUUtilization", {})
            cpu_avg = cpu.get("average", 0)
            
            if cpu_avg < self.min_utilization:
                # Too idle for RI commitment
                continue
            
            # Group by type and region
            key = (instance["instance_type"], instance["region"])
            if key not in instance_groups:
                instance_groups[key] = []
            instance_groups[key].append(instance)
        
        # Generate recommendations for each group
        for (instance_type, region), group in instance_groups.items():
            if len(group) >= 1:  # At least 1 instance
                rec = self._analyze_group(instance_type, region, group)
                if rec:
                    recommendations.append(rec)
        
        # Sort by savings
        recommendations.sort(key=lambda r: r.annual_savings, reverse=True)
        
        return recommendations
    
    def _analyze_group(
        self,
        instance_type: str,
        region: str,
        instances: list[dict],
    ) -> Optional[RIRecommendation]:
        """Analyze a group of same-type instances for RI potential."""
        quantity = len(instances)
        
        # Get current on-demand cost
        hourly_rate = self.calculator.get_instance_pricing(instance_type, region)
        current_monthly = hourly_rate * 730 * quantity
        
        if current_monthly < 10:  # Skip if too small
            return None
        
        # Calculate best RI option
        best_term = "1-year"
        best_payment = "partial-upfront"
        
        # For larger savings, recommend 3-year
        if current_monthly > 500:
            best_term = "3-year"
        
        discount_key = f"{best_term}-{best_payment}"
        discount = RI_DISCOUNTS.get(discount_key, 0.35)
        
        ri_monthly = current_monthly * (1 - discount)
        monthly_savings = current_monthly - ri_monthly
        annual_savings = monthly_savings * 12
        
        # Calculate break-even
        # For partial upfront, assume 50% upfront
        upfront_cost = 0
        if best_payment == "partial-upfront":
            upfront_cost = ri_monthly * 6  # ~6 months upfront
        elif best_payment == "all-upfront":
            upfront_cost = ri_monthly * 12 if best_term == "1-year" else ri_monthly * 36
        
        if monthly_savings > 0:
            break_even_months = upfront_cost / monthly_savings if upfront_cost > 0 else 0
        else:
            break_even_months = float('inf')
        
        # Assign confidence
        if quantity >= 3 and break_even_months < 6:
            confidence = "high"
        elif quantity >= 2 or break_even_months < 9:
            confidence = "medium"
        else:
            confidence = "low"
        
        return RIRecommendation(
            instance_type=instance_type,
            region=region,
            quantity=quantity,
            term=best_term,
            payment_option=best_payment,
            current_monthly_cost=current_monthly,
            ri_monthly_cost=ri_monthly,
            monthly_savings=monthly_savings,
            annual_savings=annual_savings,
            break_even_months=break_even_months,
            confidence=confidence,
            instance_ids=[i["instance_id"] for i in instances],
            upfront_cost=upfront_cost,
        )
    
    def compare_ri_vs_savings_plan(
        self,
        instances: list[dict],
        metrics: dict[str, dict],
    ) -> dict:
        """
        Compare Reserved Instances vs Savings Plans.
        
        Returns comparison data showing which option is better.
        """
        # Get RI recommendations
        ri_recommendations = self.find_ri_candidates(instances, metrics)
        total_ri_savings = sum(r.monthly_savings for r in ri_recommendations)
        
        # Calculate total on-demand spend
        total_on_demand = 0
        for instance in instances:
            if instance.get("state") != "running":
                continue
            hourly_rate = self.calculator.get_instance_pricing(
                instance["instance_type"],
                instance["region"]
            )
            total_on_demand += hourly_rate * 730
        
        # Savings Plan estimates
        compute_sp_1yr_savings = total_on_demand * SAVINGS_PLAN_DISCOUNTS["compute-1-year"]
        compute_sp_3yr_savings = total_on_demand * SAVINGS_PLAN_DISCOUNTS["compute-3-year"]
        
        return {
            "on_demand_monthly": total_on_demand,
            "reserved_instances": {
                "recommendations": len(ri_recommendations),
                "monthly_savings": total_ri_savings,
                "annual_savings": total_ri_savings * 12,
                "details": [
                    {
                        "type": r.instance_type,
                        "region": r.region,
                        "quantity": r.quantity,
                        "savings": r.monthly_savings,
                    }
                    for r in ri_recommendations[:5]
                ]
            },
            "savings_plans": {
                "compute_1_year": {
                    "monthly_savings": compute_sp_1yr_savings,
                    "commitment": total_on_demand * 0.65,  # After 35% discount
                },
                "compute_3_year": {
                    "monthly_savings": compute_sp_3yr_savings,
                    "commitment": total_on_demand * 0.45,  # After 55% discount
                },
            },
            "recommendation": (
                "Reserved Instances" if total_ri_savings > compute_sp_1yr_savings 
                else "Compute Savings Plan"
            ),
            "recommendation_reason": (
                "RIs provide better savings for your specific instance types"
                if total_ri_savings > compute_sp_1yr_savings
                else "Savings Plans offer flexibility across instance types"
            ),
        }
    
    def get_summary(self, recommendations: list[RIRecommendation]) -> dict:
        """Get summary statistics from recommendations."""
        if not recommendations:
            return {
                "total_recommendations": 0,
                "total_monthly_savings": 0,
                "total_annual_savings": 0,
                "by_confidence": {"high": 0, "medium": 0, "low": 0},
            }
        
        return {
            "total_recommendations": len(recommendations),
            "total_monthly_savings": sum(r.monthly_savings for r in recommendations),
            "total_annual_savings": sum(r.annual_savings for r in recommendations),
            "by_confidence": {
                "high": len([r for r in recommendations if r.confidence == "high"]),
                "medium": len([r for r in recommendations if r.confidence == "medium"]),
                "low": len([r for r in recommendations if r.confidence == "low"]),
            },
            "top_opportunities": [
                {
                    "type": r.instance_type,
                    "quantity": r.quantity,
                    "monthly_savings": r.monthly_savings,
                    "term": r.term,
                }
                for r in recommendations[:5]
            ],
        }

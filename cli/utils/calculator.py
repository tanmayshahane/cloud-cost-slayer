"""
Cost calculation utilities for AWS resources.

Provides accurate cost calculations for:
- EC2 instance pricing (on-demand, reserved)
- Savings calculations (rightsizing, scheduling, RI)
- Regional price variations
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from .logger import get_logger
from .aws_client import AWSClient, get_default_client

logger = get_logger(__name__)

# Hours per month (average)
HOURS_PER_MONTH = 730

# Common instance type pricing fallback (us-east-1, on-demand USD/hour)
# Updated as of Jan 2026
FALLBACK_PRICING: dict[str, float] = {
    # T2 family (burstable, older gen)
    "t2.nano": 0.0058,
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t2.large": 0.0928,
    "t2.xlarge": 0.1856,
    "t2.2xlarge": 0.3712,
    # T3 family
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    # T3a family (AMD)
    "t3a.nano": 0.0047,
    "t3a.micro": 0.0094,
    "t3a.small": 0.0188,
    "t3a.medium": 0.0376,
    "t3a.large": 0.0752,
    "t3a.xlarge": 0.1504,
    "t3a.2xlarge": 0.3008,
    # M5 family
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "m5.8xlarge": 1.536,
    # M5a family (AMD)
    "m5a.large": 0.086,
    "m5a.xlarge": 0.172,
    "m5a.2xlarge": 0.344,
    "m5a.4xlarge": 0.688,
    # M6i family
    "m6i.large": 0.096,
    "m6i.xlarge": 0.192,
    "m6i.2xlarge": 0.384,
    "m6i.4xlarge": 0.768,
    # M6g family (Graviton)
    "m6g.medium": 0.0385,
    "m6g.large": 0.077,
    "m6g.xlarge": 0.154,
    "m6g.2xlarge": 0.308,
    # C5 family
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,
    "c5.4xlarge": 0.68,
    # R5 family
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
}

# Instance type hierarchy for downsizing recommendations
INSTANCE_SIZE_ORDER = [
    "nano", "micro", "small", "medium", "large",
    "xlarge", "2xlarge", "4xlarge", "8xlarge", "12xlarge",
    "16xlarge", "24xlarge", "metal"
]

# Regional price multipliers (relative to us-east-1)
REGIONAL_MULTIPLIERS: dict[str, float] = {
    "us-east-1": 1.0,
    "us-east-2": 1.0,
    "us-west-1": 1.1,
    "us-west-2": 1.0,
    "eu-west-1": 1.1,
    "eu-west-2": 1.15,
    "eu-central-1": 1.15,
    "ap-south-1": 1.05,
    "ap-southeast-1": 1.1,
    "ap-southeast-2": 1.15,
    "ap-northeast-1": 1.2,
    "ap-northeast-2": 1.15,
    "sa-east-1": 1.3,
    "ca-central-1": 1.05,
}

# RI discount rates (percentage off on-demand)
RI_DISCOUNTS = {
    "1yr_no_upfront": 0.31,
    "1yr_partial_upfront": 0.36,
    "1yr_all_upfront": 0.40,
    "3yr_no_upfront": 0.45,
    "3yr_partial_upfront": 0.52,
    "3yr_all_upfront": 0.60,
}


class CostCalculator:
    """
    Calculator for AWS EC2 costs and savings.
    
    Provides methods to calculate current costs, potential savings,
    and optimization opportunities.
    """
    
    def __init__(self, aws_client: Optional[AWSClient] = None):
        """
        Initialize cost calculator.
        
        Args:
            aws_client: AWS client instance (uses default if not specified)
        """
        self.aws_client = aws_client or get_default_client()
        self._pricing_cache: dict[str, float] = {}
        self._cache_loaded = False
    
    def _load_pricing_cache(self) -> None:
        """Load pricing cache from disk if available."""
        cache_path = Path.home() / ".cloud-cost-slayer" / "pricing_cache.json"
        if cache_path.exists():
            try:
                with open(cache_path) as f:
                    data = json.load(f)
                    # Check if cache is fresh (less than 24 hours old)
                    if data.get("timestamp"):
                        cache_time = datetime.fromisoformat(data["timestamp"])
                        if datetime.now() - cache_time < timedelta(hours=24):
                            self._pricing_cache = data.get("prices", {})
                            logger.debug(f"Loaded {len(self._pricing_cache)} prices from cache")
            except Exception as e:
                logger.debug(f"Failed to load pricing cache: {e}")
        self._cache_loaded = True
    
    def _save_pricing_cache(self) -> None:
        """Save pricing cache to disk."""
        cache_path = Path.home() / ".cloud-cost-slayer" / "pricing_cache.json"
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "prices": self._pricing_cache,
                }, f)
        except Exception as e:
            logger.debug(f"Failed to save pricing cache: {e}")
    
    def get_instance_pricing(
        self,
        instance_type: str,
        region: str = "us-east-1"
    ) -> float:
        """
        Get hourly on-demand price for an instance type.
        
        Args:
            instance_type: EC2 instance type (e.g., 't3.large')
            region: AWS region
        
        Returns:
            Hourly price in USD
        """
        if not self._cache_loaded:
            self._load_pricing_cache()
        
        cache_key = f"{instance_type}:{region}"
        
        # Check cache first
        if cache_key in self._pricing_cache:
            return self._pricing_cache[cache_key]
        
        # Try to get from AWS Pricing API
        try:
            pricing = self.aws_client.get_pricing_client()
            response = pricing.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": self._region_to_location(region)},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                ],
                MaxResults=1,
            )
            
            if response.get("PriceList"):
                price_data = json.loads(response["PriceList"][0])
                terms = price_data.get("terms", {}).get("OnDemand", {})
                for term in terms.values():
                    for price_dim in term.get("priceDimensions", {}).values():
                        price = float(price_dim["pricePerUnit"]["USD"])
                        self._pricing_cache[cache_key] = price
                        self._save_pricing_cache()
                        return price
        except Exception as e:
            logger.debug(f"Pricing API error for {instance_type}: {e}")
        
        # Fallback to static pricing with regional multiplier
        base_price = FALLBACK_PRICING.get(instance_type, 0.1)
        multiplier = REGIONAL_MULTIPLIERS.get(region, 1.1)
        price = base_price * multiplier
        
        self._pricing_cache[cache_key] = price
        return price
    
    def _region_to_location(self, region: str) -> str:
        """Convert AWS region code to pricing API location name."""
        region_names = {
            "us-east-1": "US East (N. Virginia)",
            "us-east-2": "US East (Ohio)",
            "us-west-1": "US West (N. California)",
            "us-west-2": "US West (Oregon)",
            "eu-west-1": "EU (Ireland)",
            "eu-west-2": "EU (London)",
            "eu-central-1": "EU (Frankfurt)",
            "ap-south-1": "Asia Pacific (Mumbai)",
            "ap-southeast-1": "Asia Pacific (Singapore)",
            "ap-southeast-2": "Asia Pacific (Sydney)",
            "ap-northeast-1": "Asia Pacific (Tokyo)",
            "ap-northeast-2": "Asia Pacific (Seoul)",
            "sa-east-1": "South America (Sao Paulo)",
            "ca-central-1": "Canada (Central)",
        }
        return region_names.get(region, region)
    
    def calculate_monthly_cost(
        self,
        instance_type: str,
        region: str = "us-east-1",
        hours: int = HOURS_PER_MONTH
    ) -> float:
        """
        Calculate monthly cost for an instance.
        
        Args:
            instance_type: EC2 instance type
            region: AWS region
            hours: Running hours per month (default: 730)
        
        Returns:
            Monthly cost in USD
        """
        hourly_price = self.get_instance_pricing(instance_type, region)
        return hourly_price * hours
    
    def calculate_rightsizing_savings(
        self,
        current_type: str,
        recommended_type: str,
        region: str = "us-east-1"
    ) -> dict:
        """
        Calculate savings from rightsizing an instance.
        
        Args:
            current_type: Current instance type
            recommended_type: Recommended instance type
            region: AWS region
        
        Returns:
            Dictionary with savings information
        """
        current_cost = self.calculate_monthly_cost(current_type, region)
        new_cost = self.calculate_monthly_cost(recommended_type, region)
        monthly_savings = current_cost - new_cost
        
        return {
            "current_monthly_cost": round(current_cost, 2),
            "optimized_monthly_cost": round(new_cost, 2),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "savings_percentage": round((monthly_savings / current_cost) * 100, 1) if current_cost > 0 else 0,
            "roi_period_days": 0,  # Immediate for rightsizing
        }
    
    def calculate_scheduling_savings(
        self,
        instance_type: str,
        idle_hours_per_week: int,
        region: str = "us-east-1"
    ) -> dict:
        """
        Calculate savings from scheduling instance shutdowns.
        
        Args:
            instance_type: EC2 instance type
            idle_hours_per_week: Hours per week instance can be shut down
            region: AWS region
        
        Returns:
            Dictionary with savings information
        """
        hourly_price = self.get_instance_pricing(instance_type, region)
        current_monthly = self.calculate_monthly_cost(instance_type, region)
        
        # Calculate monthly idle hours (52 weeks / 12 months ≈ 4.33 weeks per month)
        monthly_idle_hours = idle_hours_per_week * 4.33
        monthly_savings = hourly_price * monthly_idle_hours
        
        return {
            "current_monthly_cost": round(current_monthly, 2),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "idle_hours_per_month": round(monthly_idle_hours, 0),
            "savings_percentage": round((monthly_savings / current_monthly) * 100, 1) if current_monthly > 0 else 0,
        }
    
    def calculate_ri_savings(
        self,
        instance_type: str,
        region: str = "us-east-1",
        term: str = "1yr_no_upfront"
    ) -> dict:
        """
        Calculate savings from Reserved Instance purchase.
        
        Args:
            instance_type: EC2 instance type
            region: AWS region
            term: RI term (e.g., '1yr_no_upfront', '3yr_all_upfront')
        
        Returns:
            Dictionary with RI savings information
        """
        current_monthly = self.calculate_monthly_cost(instance_type, region)
        discount = RI_DISCOUNTS.get(term, 0.31)
        
        monthly_savings = current_monthly * discount
        new_monthly = current_monthly - monthly_savings
        
        # Calculate break-even based on term
        term_months = 12 if term.startswith("1yr") else 36
        
        return {
            "current_monthly_cost": round(current_monthly, 2),
            "ri_monthly_cost": round(new_monthly, 2),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "total_savings": round(monthly_savings * term_months, 2),
            "savings_percentage": round(discount * 100, 1),
            "term": term,
            "break_even_months": 0 if "no_upfront" in term else (term_months // 3),
        }
    
    def find_smaller_instance_type(
        self,
        current_type: str,
        steps_down: int = 1
    ) -> Optional[str]:
        """
        Find a smaller instance type in the same family.
        
        Args:
            current_type: Current instance type (e.g., 't3.xlarge')
            steps_down: Number of sizes to step down
        
        Returns:
            Smaller instance type or None if not possible
        """
        try:
            parts = current_type.rsplit(".", 1)
            if len(parts) != 2:
                return None
            
            family, size = parts
            
            if size not in INSTANCE_SIZE_ORDER:
                return None
            
            current_index = INSTANCE_SIZE_ORDER.index(size)
            new_index = current_index - steps_down
            
            if new_index < 0:
                return None
            
            return f"{family}.{INSTANCE_SIZE_ORDER[new_index]}"
        except Exception:
            return None
    
    def get_instance_family(self, instance_type: str) -> str:
        """Extract instance family from type (e.g., 't3' from 't3.large')."""
        return instance_type.rsplit(".", 1)[0] if "." in instance_type else instance_type
    
    def get_instance_size(self, instance_type: str) -> str:
        """Extract instance size from type (e.g., 'large' from 't3.large')."""
        parts = instance_type.rsplit(".", 1)
        return parts[1] if len(parts) == 2 else "unknown"


# Singleton instance for convenience
_calculator: Optional[CostCalculator] = None


def get_calculator() -> CostCalculator:
    """Get the default cost calculator instance."""
    global _calculator
    if _calculator is None:
        _calculator = CostCalculator()
    return _calculator

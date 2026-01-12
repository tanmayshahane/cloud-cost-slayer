"""
AWS Pricing Data Collector.

Collects pricing information from AWS Pricing API:
- EC2 on-demand pricing
- Reserved Instance pricing
- Regional price variations
"""

import json
from typing import Optional
from pathlib import Path
from datetime import datetime, timedelta

from ..utils.aws_client import AWSClient, get_default_client
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Cache file location
CACHE_DIR = Path.home() / ".cloud-cost-slayer"
PRICING_CACHE_FILE = CACHE_DIR / "pricing_cache.json"
CACHE_TTL_HOURS = 24


class PricingCollector:
    """
    Collect AWS pricing information.
    
    Uses the AWS Pricing API with local caching to minimize
    API calls and provide fast lookups.
    """
    
    def __init__(self, aws_client: Optional[AWSClient] = None):
        """
        Initialize pricing collector.
        
        Args:
            aws_client: AWS client instance
        """
        self.aws_client = aws_client or get_default_client()
        self._cache: dict = {}
        self._cache_loaded = False
    
    def _load_cache(self) -> None:
        """Load pricing cache from disk."""
        if self._cache_loaded:
            return
        
        try:
            if PRICING_CACHE_FILE.exists():
                with open(PRICING_CACHE_FILE) as f:
                    data = json.load(f)
                    
                # Check cache freshness
                timestamp = data.get("timestamp")
                if timestamp:
                    cache_time = datetime.fromisoformat(timestamp)
                    if datetime.now() - cache_time < timedelta(hours=CACHE_TTL_HOURS):
                        self._cache = data.get("pricing", {})
                        logger.debug(f"Loaded {len(self._cache)} prices from cache")
        except Exception as e:
            logger.debug(f"Failed to load pricing cache: {e}")
        
        self._cache_loaded = True
    
    def _save_cache(self) -> None:
        """Save pricing cache to disk."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(PRICING_CACHE_FILE, "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "pricing": self._cache,
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save pricing cache: {e}")
    
    def get_ec2_pricing(
        self,
        instance_type: str,
        region: str = "us-east-1",
        operating_system: str = "Linux",
    ) -> Optional[dict]:
        """
        Get EC2 on-demand pricing for an instance type.
        
        Args:
            instance_type: EC2 instance type (e.g., 't3.large')
            region: AWS region
            operating_system: OS type (Linux, Windows, RHEL, SUSE)
        
        Returns:
            Pricing dictionary or None if not found
        """
        self._load_cache()
        
        cache_key = f"{instance_type}:{region}:{operating_system}"
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Fetch from API
        try:
            pricing_client = self.aws_client.get_pricing_client()
            
            response = pricing_client.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": self._region_to_location(region)},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": operating_system},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                ],
                MaxResults=1,
            )
            
            if not response.get("PriceList"):
                return None
            
            price_data = json.loads(response["PriceList"][0])
            
            # Extract on-demand pricing
            pricing = self._extract_pricing(price_data)
            
            if pricing:
                self._cache[cache_key] = pricing
                self._save_cache()
            
            return pricing
            
        except Exception as e:
            logger.debug(f"Failed to get pricing for {instance_type} in {region}: {e}")
            return None
    
    def _extract_pricing(self, price_data: dict) -> Optional[dict]:
        """
        Extract pricing information from AWS Pricing API response.
        
        Args:
            price_data: Raw pricing data from API
        
        Returns:
            Cleaned pricing dictionary
        """
        try:
            product = price_data.get("product", {})
            attributes = product.get("attributes", {})
            
            # Get on-demand terms
            terms = price_data.get("terms", {})
            on_demand = terms.get("OnDemand", {})
            
            hourly_price = 0.0
            for term in on_demand.values():
                for dim in term.get("priceDimensions", {}).values():
                    price_str = dim.get("pricePerUnit", {}).get("USD", "0")
                    hourly_price = float(price_str)
                    break
                break
            
            return {
                "instance_type": attributes.get("instanceType"),
                "vcpu": int(attributes.get("vcpu", 0)),
                "memory": attributes.get("memory"),
                "storage": attributes.get("storage"),
                "network_performance": attributes.get("networkPerformance"),
                "hourly_price": hourly_price,
                "monthly_price": round(hourly_price * 730, 2),
                "currency": "USD",
            }
            
        except Exception as e:
            logger.debug(f"Failed to extract pricing: {e}")
            return None
    
    def _region_to_location(self, region: str) -> str:
        """Convert AWS region code to pricing API location name."""
        region_names = {
            "us-east-1": "US East (N. Virginia)",
            "us-east-2": "US East (Ohio)",
            "us-west-1": "US West (N. California)",
            "us-west-2": "US West (Oregon)",
            "eu-west-1": "EU (Ireland)",
            "eu-west-2": "EU (London)",
            "eu-west-3": "EU (Paris)",
            "eu-central-1": "EU (Frankfurt)",
            "eu-north-1": "EU (Stockholm)",
            "ap-south-1": "Asia Pacific (Mumbai)",
            "ap-southeast-1": "Asia Pacific (Singapore)",
            "ap-southeast-2": "Asia Pacific (Sydney)",
            "ap-northeast-1": "Asia Pacific (Tokyo)",
            "ap-northeast-2": "Asia Pacific (Seoul)",
            "ap-northeast-3": "Asia Pacific (Osaka)",
            "sa-east-1": "South America (Sao Paulo)",
            "ca-central-1": "Canada (Central)",
            "me-south-1": "Middle East (Bahrain)",
            "af-south-1": "Africa (Cape Town)",
        }
        return region_names.get(region, region)
    
    def get_ri_pricing(
        self,
        instance_type: str,
        region: str = "us-east-1",
        term: str = "1yr",
        payment_option: str = "No Upfront",
    ) -> Optional[dict]:
        """
        Get Reserved Instance pricing.
        
        Args:
            instance_type: EC2 instance type
            region: AWS region
            term: RI term ('1yr' or '3yr')
            payment_option: Payment option ('No Upfront', 'Partial Upfront', 'All Upfront')
        
        Returns:
            RI pricing dictionary or None
        """
        # For now, estimate based on on-demand with discount
        on_demand = self.get_ec2_pricing(instance_type, region)
        if not on_demand:
            return None
        
        # Standard RI discounts
        discounts = {
            ("1yr", "No Upfront"): 0.31,
            ("1yr", "Partial Upfront"): 0.36,
            ("1yr", "All Upfront"): 0.40,
            ("3yr", "No Upfront"): 0.45,
            ("3yr", "Partial Upfront"): 0.52,
            ("3yr", "All Upfront"): 0.60,
        }
        
        discount = discounts.get((term, payment_option), 0.31)
        
        hourly = on_demand["hourly_price"]
        ri_hourly = hourly * (1 - discount)
        
        return {
            "instance_type": instance_type,
            "term": term,
            "payment_option": payment_option,
            "on_demand_hourly": hourly,
            "ri_hourly": round(ri_hourly, 4),
            "discount_percentage": round(discount * 100, 1),
            "monthly_savings": round((hourly - ri_hourly) * 730, 2),
            "annual_savings": round((hourly - ri_hourly) * 730 * 12, 2),
        }
    
    def get_instance_specs(self, instance_type: str) -> Optional[dict]:
        """
        Get instance specifications (vCPU, memory, etc.).
        
        Args:
            instance_type: EC2 instance type
        
        Returns:
            Specifications dictionary
        """
        pricing = self.get_ec2_pricing(instance_type)
        if pricing:
            return {
                "vcpu": pricing.get("vcpu"),
                "memory": pricing.get("memory"),
                "storage": pricing.get("storage"),
                "network_performance": pricing.get("network_performance"),
            }
        
        # Fallback to common instance specs
        return self._get_fallback_specs(instance_type)
    
    def _get_fallback_specs(self, instance_type: str) -> dict:
        """Get fallback instance specs for common types."""
        specs = {
            # T3 family
            "t3.nano": {"vcpu": 2, "memory": "0.5 GiB"},
            "t3.micro": {"vcpu": 2, "memory": "1 GiB"},
            "t3.small": {"vcpu": 2, "memory": "2 GiB"},
            "t3.medium": {"vcpu": 2, "memory": "4 GiB"},
            "t3.large": {"vcpu": 2, "memory": "8 GiB"},
            "t3.xlarge": {"vcpu": 4, "memory": "16 GiB"},
            "t3.2xlarge": {"vcpu": 8, "memory": "32 GiB"},
            # M5 family
            "m5.large": {"vcpu": 2, "memory": "8 GiB"},
            "m5.xlarge": {"vcpu": 4, "memory": "16 GiB"},
            "m5.2xlarge": {"vcpu": 8, "memory": "32 GiB"},
            "m5.4xlarge": {"vcpu": 16, "memory": "64 GiB"},
            # C5 family
            "c5.large": {"vcpu": 2, "memory": "4 GiB"},
            "c5.xlarge": {"vcpu": 4, "memory": "8 GiB"},
            "c5.2xlarge": {"vcpu": 8, "memory": "16 GiB"},
            "c5.4xlarge": {"vcpu": 16, "memory": "32 GiB"},
            # R5 family
            "r5.large": {"vcpu": 2, "memory": "16 GiB"},
            "r5.xlarge": {"vcpu": 4, "memory": "32 GiB"},
            "r5.2xlarge": {"vcpu": 8, "memory": "64 GiB"},
        }
        return specs.get(instance_type, {"vcpu": 0, "memory": "Unknown"})

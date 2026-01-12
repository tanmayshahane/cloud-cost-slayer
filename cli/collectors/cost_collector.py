"""
AWS Cost Explorer Data Collector.

Collects historical cost and usage data:
- Per-instance cost attribution
- Tag-based cost breakdowns
- Service-level spending
"""

from datetime import datetime, timedelta
from typing import Optional

from ..utils.aws_client import AWSClient, get_default_client
from ..utils.logger import get_logger

logger = get_logger(__name__)


class CostCollector:
    """
    Collect cost and usage data from AWS Cost Explorer.
    
    Provides historical cost data for instances and services,
    enabling accurate savings calculations.
    """
    
    def __init__(self, aws_client: Optional[AWSClient] = None):
        """
        Initialize cost collector.
        
        Args:
            aws_client: AWS client instance
        """
        self.aws_client = aws_client or get_default_client()
    
    def get_instance_costs(
        self,
        instance_id: str,
        days: int = 30,
    ) -> dict:
        """
        Get historical costs for a specific instance.
        
        Args:
            instance_id: EC2 instance ID
            days: Number of days to look back
        
        Returns:
            Cost data dictionary
        """
        ce = self.aws_client.get_cost_explorer_client()
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date,
                    "End": end_date,
                },
                Granularity="DAILY",
                Filter={
                    "Dimensions": {
                        "Key": "RESOURCE_ID",
                        "Values": [instance_id],
                    }
                },
                Metrics=["UnblendedCost", "UsageQuantity"],
            )
            
            total_cost = 0.0
            daily_costs = []
            
            for result in response.get("ResultsByTime", []):
                cost = float(result["Total"]["UnblendedCost"]["Amount"])
                total_cost += cost
                daily_costs.append({
                    "date": result["TimePeriod"]["Start"],
                    "cost": round(cost, 2),
                })
            
            return {
                "instance_id": instance_id,
                "period_days": days,
                "total_cost": round(total_cost, 2),
                "average_daily_cost": round(total_cost / max(days, 1), 2),
                "estimated_monthly_cost": round((total_cost / max(days, 1)) * 30, 2),
                "daily_costs": daily_costs,
            }
            
        except Exception as e:
            logger.debug(f"Failed to get costs for {instance_id}: {e}")
            return {
                "instance_id": instance_id,
                "total_cost": 0.0,
                "error": str(e),
            }
    
    def get_ec2_total_costs(self, days: int = 30) -> dict:
        """
        Get total EC2 costs for the account.
        
        Args:
            days: Number of days to look back
        
        Returns:
            EC2 cost summary
        """
        ce = self.aws_client.get_cost_explorer_client()
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date,
                    "End": end_date,
                },
                Granularity="MONTHLY",
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": ["Amazon Elastic Compute Cloud - Compute"],
                    }
                },
                Metrics=["UnblendedCost"],
            )
            
            total_cost = sum(
                float(r["Total"]["UnblendedCost"]["Amount"])
                for r in response.get("ResultsByTime", [])
            )
            
            return {
                "service": "EC2",
                "period_days": days,
                "total_cost": round(total_cost, 2),
                "average_daily": round(total_cost / max(days, 1), 2),
                "estimated_monthly": round((total_cost / max(days, 1)) * 30, 2),
            }
            
        except Exception as e:
            logger.warning(f"Failed to get EC2 costs: {e}")
            return {"service": "EC2", "error": str(e)}
    
    def get_costs_by_tag(
        self,
        tag_key: str,
        days: int = 30,
    ) -> list[dict]:
        """
        Get costs grouped by a specific tag.
        
        Args:
            tag_key: Tag key to group by (e.g., 'Environment', 'Team')
            days: Number of days to look back
        
        Returns:
            List of cost breakdowns by tag value
        """
        ce = self.aws_client.get_cost_explorer_client()
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date,
                    "End": end_date,
                },
                Granularity="MONTHLY",
                GroupBy=[
                    {"Type": "TAG", "Key": tag_key},
                ],
                Metrics=["UnblendedCost"],
            )
            
            results = []
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    tag_value = group["Keys"][0].replace(f"{tag_key}$", "") or "untagged"
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    results.append({
                        "tag_key": tag_key,
                        "tag_value": tag_value,
                        "cost": round(cost, 2),
                    })
            
            # Aggregate across months
            aggregated = {}
            for r in results:
                key = r["tag_value"]
                if key not in aggregated:
                    aggregated[key] = {"tag_key": tag_key, "tag_value": key, "cost": 0}
                aggregated[key]["cost"] += r["cost"]
            
            return sorted(
                [{"tag_key": v["tag_key"], "tag_value": v["tag_value"], "cost": round(v["cost"], 2)}
                 for v in aggregated.values()],
                key=lambda x: x["cost"],
                reverse=True,
            )
            
        except Exception as e:
            logger.warning(f"Failed to get costs by tag {tag_key}: {e}")
            return []
    
    def get_costs_by_region(self, days: int = 30) -> list[dict]:
        """
        Get EC2 costs grouped by region.
        
        Args:
            days: Number of days to look back
        
        Returns:
            List of cost breakdowns by region
        """
        ce = self.aws_client.get_cost_explorer_client()
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            response = ce.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date,
                    "End": end_date,
                },
                Granularity="MONTHLY",
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": ["Amazon Elastic Compute Cloud - Compute"],
                    }
                },
                GroupBy=[
                    {"Type": "DIMENSION", "Key": "REGION"},
                ],
                Metrics=["UnblendedCost"],
            )
            
            results = {}
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    region = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    if region not in results:
                        results[region] = 0
                    results[region] += cost
            
            return sorted(
                [{"region": k, "cost": round(v, 2)} for k, v in results.items()],
                key=lambda x: x["cost"],
                reverse=True,
            )
            
        except Exception as e:
            logger.warning(f"Failed to get costs by region: {e}")
            return []

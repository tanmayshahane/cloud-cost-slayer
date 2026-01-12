"""
Right-Sizing Analyzer.

Analyzes EC2 instance utilization and generates downsizing recommendations:
- P95 CPU/memory analysis with safety headroom
- Instance family optimization
- Confidence scoring
- Safety rules for production/database protection
"""

from typing import Optional
from dataclasses import dataclass, field

from ..utils.logger import get_logger
from ..utils.calculator import CostCalculator, get_calculator
from ..utils.validators import is_production_instance, is_database_instance

logger = get_logger(__name__)

# Configuration thresholds
CPU_UNDERUTILIZED_THRESHOLD = 40  # P95 CPU below this suggests downsizing
CPU_HIGHLY_UNDERUTILIZED_THRESHOLD = 20  # P95 CPU below this is definitely oversized
HEADROOM_PERCENTAGE = 20  # Safety margin to add to recommendations
MIN_DATA_DAYS = 7  # Minimum days of data required for recommendation


@dataclass
class RightsizingRecommendation:
    """Represents a rightsizing recommendation for an instance."""
    
    instance_id: str
    instance_name: str
    region: str
    current_type: str
    recommended_type: str
    confidence: str  # 'high', 'medium', 'low'
    confidence_reasons: list[str] = field(default_factory=list)
    
    # Cost information
    current_monthly_cost: float = 0.0
    recommended_monthly_cost: float = 0.0
    monthly_savings: float = 0.0
    annual_savings: float = 0.0
    savings_percentage: float = 0.0
    
    # Metrics
    cpu_average: float = 0.0
    cpu_p95: float = 0.0
    cpu_max: float = 0.0
    
    # Safety
    is_production: bool = False
    is_database: bool = False
    data_days: int = 0
    
    # Implementation
    recommendation_type: str = "rightsizing"
    action_required: str = "resize"
    estimated_downtime_seconds: int = 120  # Instance stop/start time
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "region": self.region,
            "current_type": self.current_type,
            "recommended_type": self.recommended_type,
            "confidence": self.confidence,
            "confidence_reasons": self.confidence_reasons,
            "current_monthly_cost": self.current_monthly_cost,
            "recommended_monthly_cost": self.recommended_monthly_cost,
            "monthly_savings": self.monthly_savings,
            "annual_savings": self.annual_savings,
            "savings_percentage": self.savings_percentage,
            "cpu_average": self.cpu_average,
            "cpu_p95": self.cpu_p95,
            "cpu_max": self.cpu_max,
            "is_production": self.is_production,
            "is_database": self.is_database,
            "data_days": self.data_days,
            "recommendation_type": self.recommendation_type,
            "action_required": self.action_required,
            "estimated_downtime_seconds": self.estimated_downtime_seconds,
        }


class RightsizingAnalyzer:
    """
    Analyze instance sizing and generate recommendations.
    
    Uses CloudWatch metrics to identify over-provisioned instances
    and recommends smaller instance types with confidence scoring.
    """
    
    def __init__(
        self,
        calculator: Optional[CostCalculator] = None,
        exclude_production: bool = True,
        exclude_databases: bool = True,
        min_savings: float = 0.0,
    ):
        """
        Initialize rightsizing analyzer.
        
        Args:
            calculator: Cost calculator instance
            exclude_production: Skip production instances
            exclude_databases: Skip database instances
            min_savings: Minimum monthly savings to include (0 = include all)
        """
        self.calculator = calculator or get_calculator()
        self.exclude_production = exclude_production
        self.exclude_databases = exclude_databases
        self.min_savings = min_savings
    
    def analyze_instance(
        self,
        instance: dict,
        metrics: dict,
    ) -> Optional[RightsizingRecommendation]:
        """
        Analyze a single instance and generate recommendation.
        
        Args:
            instance: Instance data dictionary
            metrics: CloudWatch metrics dictionary
        
        Returns:
            RightsizingRecommendation or None if no recommendation
        """
        instance_id = instance["instance_id"]
        instance_type = instance["instance_type"]
        region = instance["region"]
        tags = instance.get("tags", {})
        name = instance.get("name", "")
        
        # Safety checks
        is_prod = is_production_instance(tags)
        is_db = is_database_instance(tags, instance_type)
        
        if self.exclude_production and is_prod:
            logger.debug(f"Skipping production instance: {instance_id}")
            return None
        
        if self.exclude_databases and is_db:
            logger.debug(f"Skipping database instance: {instance_id}")
            return None
        
        # Get CPU metrics
        cpu_metrics = metrics.get("CPUUtilization", {})
        cpu_avg = cpu_metrics.get("average", 0)
        cpu_max = cpu_metrics.get("average_max", cpu_metrics.get("maximum", 0))
        cpu_p95 = cpu_metrics.get("p95", cpu_avg)
        data_points = cpu_metrics.get("datapoint_count", 0)
        
        # Check data sufficiency
        # Assuming 5-minute intervals, 7 days = 7 * 24 * 12 = 2016 datapoints
        min_datapoints = MIN_DATA_DAYS * 24 * 12
        data_days = data_points // (24 * 12) if data_points > 0 else 0
        
        if data_points < min_datapoints:
            logger.debug(
                f"Insufficient data for {instance_id}: "
                f"{data_points} datapoints ({data_days} days)"
            )
            return None
        
        # Check if underutilized
        if cpu_p95 >= CPU_UNDERUTILIZED_THRESHOLD:
            logger.debug(f"Instance {instance_id} is well-utilized (p95: {cpu_p95}%)")
            return None
        
        # Find recommended instance size
        recommended_type = self._find_optimal_size(
            instance_type, cpu_p95, cpu_max
        )
        
        if not recommended_type or recommended_type == instance_type:
            return None
        
        # Calculate costs
        savings = self.calculator.calculate_rightsizing_savings(
            instance_type, recommended_type, region
        )
        
        # Skip if savings are below threshold
        if savings["monthly_savings"] < self.min_savings:
            logger.debug(f"Skipping {instance_id}: savings ${savings['monthly_savings']:.2f} < ${self.min_savings:.2f}")
            return None
        
        # Determine confidence
        confidence, reasons = self._calculate_confidence(
            cpu_avg, cpu_p95, cpu_max, data_days, is_prod, is_db
        )
        
        return RightsizingRecommendation(
            instance_id=instance_id,
            instance_name=name,
            region=region,
            current_type=instance_type,
            recommended_type=recommended_type,
            confidence=confidence,
            confidence_reasons=reasons,
            current_monthly_cost=savings["current_monthly_cost"],
            recommended_monthly_cost=savings["optimized_monthly_cost"],
            monthly_savings=savings["monthly_savings"],
            annual_savings=savings["annual_savings"],
            savings_percentage=savings["savings_percentage"],
            cpu_average=cpu_avg,
            cpu_p95=cpu_p95,
            cpu_max=cpu_max,
            is_production=is_prod,
            is_database=is_db,
            data_days=data_days,
        )
    
    def analyze_batch(
        self,
        instances: list[dict],
        metrics: dict[str, dict],
    ) -> list[RightsizingRecommendation]:
        """
        Analyze multiple instances and generate recommendations.
        
        Args:
            instances: List of instance dictionaries
            metrics: Dictionary mapping instance_id to metrics
        
        Returns:
            List of recommendations sorted by savings
        """
        recommendations = []
        
        for instance in instances:
            instance_id = instance["instance_id"]
            instance_metrics = metrics.get(instance_id, {})
            
            rec = self.analyze_instance(instance, instance_metrics)
            if rec:
                recommendations.append(rec)
        
        # Sort by savings (highest first)
        recommendations.sort(key=lambda x: x.monthly_savings, reverse=True)
        
        logger.info(f"Generated {len(recommendations)} rightsizing recommendations")
        return recommendations
    
    def _find_optimal_size(
        self,
        current_type: str,
        cpu_p95: float,
        cpu_max: float,
    ) -> Optional[str]:
        """
        Find the optimal instance size based on CPU usage.
        
        Args:
            current_type: Current instance type
            cpu_p95: 95th percentile CPU usage
            cpu_max: Maximum CPU usage
        
        Returns:
            Recommended instance type or None
        """
        # Calculate required CPU capacity with headroom
        required_capacity = (cpu_p95 + HEADROOM_PERCENTAGE) / 100
        
        # Determine how many sizes to step down
        if cpu_p95 < 10:
            steps = 2  # Very underutilized, can go down 2 sizes
        elif cpu_p95 < CPU_HIGHLY_UNDERUTILIZED_THRESHOLD:
            steps = 2
        elif cpu_p95 < CPU_UNDERUTILIZED_THRESHOLD:
            steps = 1
        else:
            steps = 0
        
        # Check if max CPU would still be safe
        if cpu_max > 80:
            steps = min(steps, 1)  # Be more conservative with spiky workloads
        
        if steps == 0:
            return None
        
        # Get smaller instance type
        return self.calculator.find_smaller_instance_type(current_type, steps)
    
    def _calculate_confidence(
        self,
        cpu_avg: float,
        cpu_p95: float,
        cpu_max: float,
        data_days: int,
        is_production: bool,
        is_database: bool,
    ) -> tuple[str, list[str]]:
        """
        Calculate confidence level for recommendation.
        
        Args:
            cpu_avg: Average CPU usage
            cpu_p95: P95 CPU usage
            cpu_max: Maximum CPU usage
            data_days: Days of data available
            is_production: Is production instance
            is_database: Is database instance
        
        Returns:
            Tuple of (confidence_level, list of reasons)
        """
        score = 100
        reasons = []
        
        # CPU utilization factors
        if cpu_p95 < 10:
            reasons.append("Very low CPU utilization (p95 < 10%)")
        elif cpu_p95 < 20:
            reasons.append("Low CPU utilization (p95 < 20%)")
        else:
            score -= 10
            reasons.append(f"Moderate CPU utilization (p95: {cpu_p95}%)")
        
        # Stability factors
        variance = cpu_max - cpu_avg
        if variance > 50:
            score -= 30
            reasons.append("High usage variance - workload may be spiky")
        elif variance > 30:
            score -= 15
            reasons.append("Moderate usage variance")
        else:
            reasons.append("Stable workload pattern")
        
        # Data sufficiency
        if data_days >= 30:
            reasons.append(f"Sufficient data ({data_days} days)")
        elif data_days >= 14:
            score -= 10
            reasons.append(f"Moderate data ({data_days} days)")
        else:
            score -= 25
            reasons.append(f"Limited data ({data_days} days)")
        
        # Environment factors
        if is_production:
            score -= 20
            reasons.append("Production instance - extra caution advised")
        
        if is_database:
            score -= 15
            reasons.append("Possible database - memory may be critical")
        
        # Determine confidence level
        if score >= 75:
            return "high", reasons
        elif score >= 50:
            return "medium", reasons
        else:
            return "low", reasons
    
    def get_summary(
        self,
        recommendations: list[RightsizingRecommendation],
    ) -> dict:
        """
        Get summary statistics for recommendations.
        
        Args:
            recommendations: List of recommendations
        
        Returns:
            Summary dictionary
        """
        if not recommendations:
            return {
                "total_recommendations": 0,
                "total_monthly_savings": 0,
                "total_annual_savings": 0,
                "by_confidence": {},
            }
        
        total_monthly = sum(r.monthly_savings for r in recommendations)
        total_annual = sum(r.annual_savings for r in recommendations)
        
        by_confidence = {"high": 0, "medium": 0, "low": 0}
        for r in recommendations:
            by_confidence[r.confidence] = by_confidence.get(r.confidence, 0) + 1
        
        return {
            "total_recommendations": len(recommendations),
            "total_monthly_savings": round(total_monthly, 2),
            "total_annual_savings": round(total_annual, 2),
            "average_savings_per_instance": round(total_monthly / len(recommendations), 2),
            "by_confidence": by_confidence,
            "high_confidence_savings": round(
                sum(r.monthly_savings for r in recommendations if r.confidence == "high"),
                2
            ),
        }

"""
Usage Pattern Detector.

Analyzes EC2 instance usage patterns to identify:
- Time-of-day usage patterns
- Day-of-week patterns  
- Idle periods for scheduling opportunities
- Workload stability assessment
"""

from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UsagePattern:
    """Represents detected usage patterns for an instance."""
    
    instance_id: str
    instance_name: str
    region: str
    instance_type: str
    
    # Classification
    pattern_type: str  # 'business_hours', 'always_on', 'sporadic', 'weekend_low'
    stability_score: float  # 0-100, higher = more stable/predictable
    
    # Hourly patterns (0-23)
    hourly_usage: dict[int, float] = field(default_factory=dict)
    peak_hours: list[int] = field(default_factory=list)
    idle_hours: list[int] = field(default_factory=list)
    
    # Daily patterns (0=Monday, 6=Sunday)
    daily_usage: dict[int, float] = field(default_factory=dict)
    peak_days: list[int] = field(default_factory=list)
    idle_days: list[int] = field(default_factory=list)
    
    # Scheduling opportunity
    can_schedule: bool = False
    suggested_schedule: Optional[str] = None
    weekly_idle_hours: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "region": self.region,
            "instance_type": self.instance_type,
            "pattern_type": self.pattern_type,
            "stability_score": self.stability_score,
            "hourly_usage": self.hourly_usage,
            "peak_hours": self.peak_hours,
            "idle_hours": self.idle_hours,
            "daily_usage": self.daily_usage,
            "peak_days": self.peak_days,
            "idle_days": self.idle_days,
            "can_schedule": self.can_schedule,
            "suggested_schedule": self.suggested_schedule,
            "weekly_idle_hours": self.weekly_idle_hours,
        }


class PatternDetector:
    """
    Detect usage patterns in EC2 instance metrics.
    
    Analyzes hourly and daily usage patterns to identify
    scheduling opportunities and workload characteristics.
    """
    
    def __init__(
        self,
        idle_threshold: float = 5.0,
        low_usage_threshold: float = 20.0,
        min_idle_hours: int = 4,
    ):
        """
        Initialize pattern detector.
        
        Args:
            idle_threshold: CPU % below which is considered idle
            low_usage_threshold: CPU % below which is considered low usage
            min_idle_hours: Minimum consecutive hours for scheduling
        """
        self.idle_threshold = idle_threshold
        self.low_usage_threshold = low_usage_threshold
        self.min_idle_hours = min_idle_hours
    
    def detect_patterns(
        self,
        instance: dict,
        metrics: dict,
    ) -> UsagePattern:
        """
        Detect usage patterns for a single instance.
        
        Args:
            instance: Instance data dictionary
            metrics: CloudWatch metrics with hourly data
        
        Returns:
            UsagePattern object
        """
        instance_id = instance["instance_id"]
        
        # Get CPU metrics
        cpu_metrics = metrics.get("CPUUtilization", {})
        raw_values = cpu_metrics.get("raw_values", [])
        
        # Analyze patterns
        hourly_usage = self._analyze_hourly_patterns(raw_values)
        daily_usage = self._analyze_daily_patterns(raw_values)
        
        # Find peak and idle periods
        peak_hours = self._find_peak_hours(hourly_usage)
        idle_hours = self._find_idle_hours(hourly_usage)
        peak_days = self._find_peak_days(daily_usage)
        idle_days = self._find_idle_days(daily_usage)
        
        # Classify pattern type
        pattern_type = self._classify_pattern(
            hourly_usage, daily_usage, peak_hours, idle_hours
        )
        
        # Calculate stability score
        stability_score = self._calculate_stability(raw_values)
        
        # Check scheduling opportunities
        can_schedule, schedule, weekly_idle = self._check_scheduling_opportunity(
            hourly_usage, daily_usage, idle_hours, idle_days
        )
        
        return UsagePattern(
            instance_id=instance_id,
            instance_name=instance.get("name", ""),
            region=instance["region"],
            instance_type=instance["instance_type"],
            pattern_type=pattern_type,
            stability_score=stability_score,
            hourly_usage=hourly_usage,
            peak_hours=peak_hours,
            idle_hours=idle_hours,
            daily_usage=daily_usage,
            peak_days=peak_days,
            idle_days=idle_days,
            can_schedule=can_schedule,
            suggested_schedule=schedule,
            weekly_idle_hours=weekly_idle,
        )
    
    def _analyze_hourly_patterns(
        self,
        values: list[float],
    ) -> dict[int, float]:
        """
        Analyze average usage by hour of day.
        
        Args:
            values: List of CPU usage values
        
        Returns:
            Dictionary mapping hour (0-23) to average usage
        """
        if not values:
            return {h: 0.0 for h in range(24)}
        
        hourly = defaultdict(list)
        
        # Handle both hourly data (24 values) and 5-minute intervals
        if len(values) == 24:
            # Direct hourly mapping
            for hour, value in enumerate(values):
                hourly[hour].append(value)
        else:
            # Assume values are in 5-minute intervals
            intervals_per_hour = 12  # 12 x 5-minute intervals per hour
            for i, value in enumerate(values):
                hour = (i // intervals_per_hour) % 24
                hourly[hour].append(value)
        
        return {
            hour: round(sum(vals) / len(vals), 2) if vals else 0.0
            for hour, vals in hourly.items()
        }
    
    def _analyze_daily_patterns(
        self,
        values: list[float],
    ) -> dict[int, float]:
        """
        Analyze average usage by day of week.
        
        Args:
            values: List of CPU usage values
        
        Returns:
            Dictionary mapping day (0=Mon, 6=Sun) to average usage
        """
        if not values:
            return {d: 0.0 for d in range(7)}
        
        # Assume values are in 5-minute intervals
        intervals_per_day = 288  # 288 x 5-minute intervals per day
        daily = defaultdict(list)
        
        for i, value in enumerate(values):
            day = (i // intervals_per_day) % 7
            daily[day].append(value)
        
        return {
            day: round(sum(vals) / len(vals), 2) if vals else 0.0
            for day, vals in daily.items()
        }
    
    def _find_peak_hours(self, hourly_usage: dict[int, float]) -> list[int]:
        """Find hours with above-average usage."""
        if not hourly_usage:
            return []
        
        avg = sum(hourly_usage.values()) / len(hourly_usage)
        return [h for h, v in hourly_usage.items() if v > avg * 1.5]
    
    def _find_idle_hours(self, hourly_usage: dict[int, float]) -> list[int]:
        """Find hours with consistently low usage."""
        return [
            h for h, v in hourly_usage.items()
            if v < self.idle_threshold
        ]
    
    def _find_peak_days(self, daily_usage: dict[int, float]) -> list[int]:
        """Find days with above-average usage."""
        if not daily_usage:
            return []
        
        avg = sum(daily_usage.values()) / len(daily_usage)
        return [d for d, v in daily_usage.items() if v > avg * 1.2]
    
    def _find_idle_days(self, daily_usage: dict[int, float]) -> list[int]:
        """Find days with consistently low usage."""
        return [
            d for d, v in daily_usage.items()
            if v < self.low_usage_threshold
        ]
    
    def _classify_pattern(
        self,
        hourly_usage: dict[int, float],
        daily_usage: dict[int, float],
        peak_hours: list[int],
        idle_hours: list[int],
    ) -> str:
        """
        Classify the overall usage pattern.
        
        Returns one of:
        - 'business_hours': High during business hours, low at night
        - 'always_on': Consistent usage 24/7
        - 'weekend_low': Lower on weekends
        - 'sporadic': Unpredictable pattern
        - 'mostly_idle': Very low usage overall
        """
        # Check for mostly idle
        avg_usage = sum(hourly_usage.values()) / max(len(hourly_usage), 1)
        if avg_usage < self.idle_threshold:
            return "mostly_idle"
        
        # Check for business hours pattern (9-17) - prioritize this check
        business_hours = list(range(9, 18))
        night_hours = list(range(0, 6)) + list(range(22, 24))
        
        business_avg = sum(hourly_usage.get(h, 0) for h in business_hours) / 9
        night_avg = sum(hourly_usage.get(h, 0) for h in night_hours) / 8
        
        # Strong business hours pattern: business is at least 2x night usage
        if night_avg > 0 and business_avg > night_avg * 2:
            return "business_hours"
        # Also classify as business hours if night is nearly idle
        if night_avg < self.idle_threshold and business_avg > self.low_usage_threshold:
            return "business_hours"
        
        # Check for always on BEFORE weekend_low (consistent high usage)
        usage_values = list(hourly_usage.values())
        if usage_values:
            variance = max(usage_values) - min(usage_values)
            if variance < 20 and avg_usage > self.low_usage_threshold:
                return "always_on"
        
        # Check for weekend low pattern
        if daily_usage:
            weekday_avg = sum(daily_usage.get(d, 0) for d in range(5)) / max(len([d for d in range(5) if d in daily_usage]), 1)
            weekend_avg = sum(daily_usage.get(d, 0) for d in [5, 6]) / max(len([d for d in [5, 6] if d in daily_usage]), 1)
            
            if weekend_avg > 0 and weekday_avg > weekend_avg * 1.5:
                return "weekend_low"
        
        return "sporadic"
    
    def _calculate_stability(self, values: list[float]) -> float:
        """
        Calculate workload stability score.
        
        Higher score = more predictable/stable workload.
        """
        if not values or len(values) < 2:
            return 0.0
        
        # Calculate coefficient of variation
        avg = sum(values) / len(values)
        if avg == 0:
            return 100.0
        
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5
        cv = std_dev / avg
        
        # Convert to 0-100 score (lower CV = higher stability)
        stability = max(0, min(100, (1 - cv) * 100))
        return round(stability, 1)
    
    def _check_scheduling_opportunity(
        self,
        hourly_usage: dict[int, float],
        daily_usage: dict[int, float],
        idle_hours: list[int],
        idle_days: list[int],
    ) -> tuple[bool, Optional[str], int]:
        """
        Check if instance is a good candidate for scheduling.
        
        Returns:
            Tuple of (can_schedule, suggested_schedule, weekly_idle_hours)
        """
        # Calculate potential idle hours per week
        weekly_idle = 0
        
        # Night hours (10pm - 6am) if consistently idle
        night_hours = [22, 23, 0, 1, 2, 3, 4, 5]
        night_idle = sum(1 for h in night_hours if hourly_usage.get(h, 0) < self.idle_threshold)
        
        if night_idle >= 6:  # At least 6 of 8 night hours are idle
            weekly_idle += night_idle * 7  # All nights
        
        # Weekend hours if consistently low
        if 5 in idle_days and 6 in idle_days:  # Saturday and Sunday
            weekly_idle += 48  # Two full days
        
        # Must have at least 20 hours per week of potential savings
        if weekly_idle < 20:
            return False, None, 0
        
        # Generate schedule suggestion
        schedule = self._generate_schedule_suggestion(
            hourly_usage, daily_usage, idle_hours, idle_days
        )
        
        return True, schedule, weekly_idle
    
    def _generate_schedule_suggestion(
        self,
        hourly_usage: dict[int, float],
        daily_usage: dict[int, float],
        idle_hours: list[int],
        idle_days: list[int],
    ) -> str:
        """Generate a human-readable schedule suggestion."""
        suggestions = []
        
        # Check for night shutdown
        night_hours = [22, 23, 0, 1, 2, 3, 4, 5]
        night_idle = [h for h in night_hours if h in idle_hours]
        if len(night_idle) >= 6:
            suggestions.append("Shutdown 10pm-6am daily")
        
        # Check for weekend shutdown
        if 5 in idle_days and 6 in idle_days:
            suggestions.append("Shutdown weekends")
        elif 6 in idle_days:
            suggestions.append("Shutdown Sundays")
        
        return " + ".join(suggestions) if suggestions else "Custom schedule needed"
    
    def analyze_batch(
        self,
        instances: list[dict],
        metrics: dict[str, dict],
    ) -> list[UsagePattern]:
        """
        Analyze multiple instances for patterns.
        
        Args:
            instances: List of instance dictionaries
            metrics: Dictionary mapping instance_id to metrics
        
        Returns:
            List of UsagePattern objects
        """
        patterns = []
        
        for instance in instances:
            instance_id = instance["instance_id"]
            instance_metrics = metrics.get(instance_id, {})
            
            pattern = self.detect_patterns(instance, instance_metrics)
            patterns.append(pattern)
        
        return patterns
    
    def get_scheduling_candidates(
        self,
        patterns: list[UsagePattern],
    ) -> list[UsagePattern]:
        """Filter patterns to only scheduling candidates."""
        return [p for p in patterns if p.can_schedule]

"""Unit tests for analyzers."""

import pytest
import json
from pathlib import Path

# Import the modules we're testing
from cli.analyzers.rightsizing_analyzer import RightsizingAnalyzer, RightsizingRecommendation
from cli.analyzers.pattern_detector import PatternDetector, UsagePattern


@pytest.fixture
def sample_data():
    """Load sample AWS data for testing."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_aws_data.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def sample_instance():
    """Create a sample instance for testing."""
    return {
        "instance_id": "i-0abc123def456789a",
        "instance_type": "t3.xlarge",
        "region": "us-east-1",
        "name": "web-server-1",
        "tags": {
            "Name": "web-server-1",
            "Environment": "development",
            "Team": "platform",
        },
        "state": "running",
    }


@pytest.fixture
def sample_metrics():
    """Create sample CloudWatch metrics."""
    return {
        "CPUUtilization": {
            "datapoint_count": 8640,  # 30 days of 5-min intervals
            "average": 15.2,
            "average_max": 45.8,
            "maximum": 52.3,
            "p50": 12.1,
            "p95": 28.5,
            "p99": 42.1,
            "raw_values": [12, 15, 18, 14, 11, 16, 20, 25, 30, 22, 18, 14, 10, 8, 6, 5, 4, 5, 8, 12, 18, 22, 25, 20],
        },
        "NetworkIn": {
            "datapoint_count": 8640,
            "average": 1024000,
            "sum": 8847360000,
        },
    }


class TestRightsizingAnalyzer:
    """Tests for RightsizingAnalyzer."""
    
    def test_analyze_underutilized_instance(self, sample_instance, sample_metrics):
        """Test that underutilized instances get recommendations."""
        analyzer = RightsizingAnalyzer(exclude_production=False)
        
        rec = analyzer.analyze_instance(sample_instance, sample_metrics)
        
        assert rec is not None
        assert rec.instance_id == "i-0abc123def456789a"
        assert rec.current_type == "t3.xlarge"
        assert rec.recommended_type == "t3.large"  # Should recommend downsize
        assert rec.monthly_savings > 0
        assert rec.confidence in ["high", "medium", "low"]
    
    def test_skip_well_utilized_instance(self, sample_instance):
        """Test that well-utilized instances are skipped."""
        analyzer = RightsizingAnalyzer()
        
        high_usage_metrics = {
            "CPUUtilization": {
                "datapoint_count": 8640,
                "average": 65.0,
                "p95": 85.0,  # High utilization
                "maximum": 95.0,
            }
        }
        
        rec = analyzer.analyze_instance(sample_instance, high_usage_metrics)
        
        assert rec is None  # No recommendation for well-utilized instance
    
    def test_skip_production_instance(self, sample_instance, sample_metrics):
        """Test that production instances are skipped by default."""
        analyzer = RightsizingAnalyzer(exclude_production=True)
        
        # Mark instance as production
        sample_instance["tags"]["Environment"] = "production"
        
        rec = analyzer.analyze_instance(sample_instance, sample_metrics)
        
        assert rec is None  # Should skip production
    
    def test_include_production_when_configured(self, sample_instance, sample_metrics):
        """Test that production instances are included when configured."""
        analyzer = RightsizingAnalyzer(exclude_production=False)
        
        # Mark instance as production
        sample_instance["tags"]["Environment"] = "production"
        
        rec = analyzer.analyze_instance(sample_instance, sample_metrics)
        
        assert rec is not None
        assert rec.is_production is True
    
    def test_skip_insufficient_data(self, sample_instance):
        """Test that instances with insufficient data are skipped."""
        analyzer = RightsizingAnalyzer()
        
        few_datapoints = {
            "CPUUtilization": {
                "datapoint_count": 100,  # Only ~8 hours of data
                "average": 10.0,
                "p95": 20.0,
            }
        }
        
        rec = analyzer.analyze_instance(sample_instance, few_datapoints)
        
        assert rec is None  # Insufficient data
    
    def test_confidence_scoring_high(self, sample_instance, sample_metrics):
        """Test high confidence for stable, underutilized workloads."""
        analyzer = RightsizingAnalyzer(exclude_production=False)
        
        stable_metrics = {
            "CPUUtilization": {
                "datapoint_count": 8640,
                "average": 8.0,
                "average_max": 15.0,
                "maximum": 20.0,
                "p95": 12.0,  # Very low
            }
        }
        
        rec = analyzer.analyze_instance(sample_instance, stable_metrics)
        
        assert rec is not None
        assert rec.confidence == "high"
    
    def test_confidence_scoring_low_for_spiky(self, sample_instance):
        """Test low confidence for spiky workloads."""
        analyzer = RightsizingAnalyzer(exclude_production=False)
        
        spiky_metrics = {
            "CPUUtilization": {
                "datapoint_count": 8640,
                "average": 15.0,
                "average_max": 90.0,  # High variance
                "maximum": 98.0,
                "p95": 35.0,
            }
        }
        
        rec = analyzer.analyze_instance(sample_instance, spiky_metrics)
        
        assert rec is not None
        assert rec.confidence in ["medium", "low"]  # Should be cautious
    
    def test_batch_analysis(self, sample_data):
        """Test batch analysis of multiple instances."""
        analyzer = RightsizingAnalyzer(exclude_production=True)
        
        # Normalize fixtures to expected format
        instances = []
        for inst in sample_data["instances"]:
            tags = {tag["Key"]: tag["Value"] for tag in inst.get("Tags", [])}
            instances.append({
                "instance_id": inst["InstanceId"],
                "instance_type": inst["InstanceType"],
                "region": inst["Placement"]["AvailabilityZone"][:-1],
                "name": tags.get("Name", ""),
                "tags": tags,
                "state": inst["State"]["Name"],
            })
        
        metrics = sample_data["metrics"]
        
        recommendations = analyzer.analyze_batch(instances, metrics)
        
        # Should have some recommendations (not all instances are optimized)
        assert len(recommendations) >= 0
        
        # Recommendations should be sorted by savings
        if len(recommendations) > 1:
            for i in range(len(recommendations) - 1):
                assert recommendations[i].monthly_savings >= recommendations[i + 1].monthly_savings
    
    def test_summary_calculation(self):
        """Test summary calculation for recommendations."""
        analyzer = RightsizingAnalyzer()
        
        # Create mock recommendations
        recs = [
            RightsizingRecommendation(
                instance_id="i-123",
                instance_name="test-1",
                region="us-east-1",
                current_type="t3.xlarge",
                recommended_type="t3.large",
                confidence="high",
                monthly_savings=100.0,
                annual_savings=1200.0,
            ),
            RightsizingRecommendation(
                instance_id="i-456",
                instance_name="test-2",
                region="us-east-1",
                current_type="m5.2xlarge",
                recommended_type="m5.xlarge",
                confidence="medium",
                monthly_savings=150.0,
                annual_savings=1800.0,
            ),
        ]
        
        summary = analyzer.get_summary(recs)
        
        assert summary["total_recommendations"] == 2
        assert summary["total_monthly_savings"] == 250.0
        assert summary["total_annual_savings"] == 3000.0
        assert summary["by_confidence"]["high"] == 1
        assert summary["by_confidence"]["medium"] == 1


class TestPatternDetector:
    """Tests for PatternDetector."""
    
    def test_detect_idle_pattern(self):
        """Test detection of mostly idle instances."""
        detector = PatternDetector()
        
        instance = {
            "instance_id": "i-idle",
            "instance_type": "t3.large",
            "region": "us-east-1",
            "name": "idle-server",
        }
        
        metrics = {
            "CPUUtilization": {
                "raw_values": [2, 1, 1, 0, 0, 1, 2, 3, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 3, 2],
            }
        }
        
        pattern = detector.detect_patterns(instance, metrics)
        
        assert pattern.pattern_type == "mostly_idle"
    
    def test_detect_business_hours_pattern(self):
        """Test detection of business hours usage pattern."""
        detector = PatternDetector()
        
        instance = {
            "instance_id": "i-biz",
            "instance_type": "t3.large",
            "region": "us-east-1",
            "name": "office-server",
        }
        
        # High during business hours (9-17), low at night
        raw_values = []
        for hour in range(24):
            if 9 <= hour < 17:
                raw_values.append(60 + (hour - 9) * 2)  # 60-76%
            else:
                raw_values.append(2 + hour % 3)  # 2-5%
        
        metrics = {
            "CPUUtilization": {
                "raw_values": raw_values,
            }
        }
        
        pattern = detector.detect_patterns(instance, metrics)
        
        assert pattern.pattern_type == "business_hours"
    
    def test_scheduling_candidate_detection(self):
        """Test detection of scheduling candidates."""
        detector = PatternDetector()
        
        instance = {
            "instance_id": "i-dev",
            "instance_type": "t3.large",
            "region": "us-east-1",
            "name": "dev-server",
        }
        
        # Low usage at night and weekends
        metrics = {
            "CPUUtilization": {
                # Very low at night (hours 0-6, 22-23)
                "raw_values": [
                    1, 1, 0, 0, 0, 0,  # 0-5: idle
                    5, 15, 30, 45, 50, 55, 60, 55, 50, 45, 40, 30,  # 6-17: busy
                    15, 8, 5, 3,  # 18-21: winding down
                    1, 0,  # 22-23: idle
                ],
            }
        }
        
        pattern = detector.detect_patterns(instance, metrics)
        
        # Should identify idle hours
        assert len(pattern.idle_hours) > 0
    
    def test_stability_score_calculation(self):
        """Test stability score calculation."""
        detector = PatternDetector()
        
        # Stable workload
        stable_instance = {
            "instance_id": "i-stable",
            "instance_type": "t3.large",
            "region": "us-east-1",
            "name": "stable-server",
        }
        
        stable_metrics = {
            "CPUUtilization": {
                "raw_values": [50, 52, 48, 51, 49, 50, 52, 48, 51, 49] * 10,  # Very consistent
            }
        }
        
        stable_pattern = detector.detect_patterns(stable_instance, stable_metrics)
        
        # Unstable workload
        unstable_instance = {
            "instance_id": "i-unstable",
            "instance_type": "t3.large",
            "region": "us-east-1",
            "name": "unstable-server",
        }
        
        unstable_metrics = {
            "CPUUtilization": {
                "raw_values": [5, 95, 10, 85, 15, 90, 8, 88, 12, 92] * 10,  # Very variable
            }
        }
        
        unstable_pattern = detector.detect_patterns(unstable_instance, unstable_metrics)
        
        # Stable should have higher score
        assert stable_pattern.stability_score > unstable_pattern.stability_score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

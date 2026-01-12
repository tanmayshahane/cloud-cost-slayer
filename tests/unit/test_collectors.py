"""Unit tests for collectors."""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Import the modules we're testing
from cli.collectors.ec2_collector import EC2Collector
from cli.collectors.cloudwatch_collector import CloudWatchCollector


@pytest.fixture
def sample_data():
    """Load sample AWS data for testing."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_aws_data.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = Mock()
    client.profile = "test"
    client.default_region = "us-east-1"
    return client


class TestEC2Collector:
    """Tests for EC2Collector."""
    
    def test_normalize_instance(self, sample_data, mock_aws_client):
        """Test instance normalization."""
        collector = EC2Collector(mock_aws_client)
        
        raw_instance = sample_data["instances"][0]
        
        # Add LaunchTime as datetime
        raw_instance["LaunchTime"] = datetime(2025, 6, 1)
        
        normalized = collector._normalize_instance(raw_instance, "us-east-1")
        
        assert normalized["instance_id"] == "i-0abc123def456789a"
        assert normalized["instance_type"] == "t3.xlarge"
        assert normalized["region"] == "us-east-1"
        assert normalized["name"] == "web-server-1"
        assert "Environment" in normalized["tags"]
        assert normalized["tags"]["Environment"] == "development"
    
    def test_tag_matching(self, mock_aws_client):
        """Test tag matching logic."""
        collector = EC2Collector(mock_aws_client)
        
        instance_tags = {
            "Environment": "production",
            "Team": "platform",
            "Name": "web-server-1",
        }
        
        # Exact match
        assert collector._matches_tags(instance_tags, [("Environment", "production")]) is True
        
        # Partial match (case-insensitive)
        assert collector._matches_tags(instance_tags, [("Environment", "prod")]) is True
        
        # No match
        assert collector._matches_tags(instance_tags, [("Environment", "staging")]) is False
        
        # Wildcard match
        assert collector._matches_tags(instance_tags, [("Environment", "*")]) is True
    
    def test_filter_by_exclude_tags(self, mock_aws_client, sample_data):
        """Test filtering instances by exclude tags."""
        collector = EC2Collector(mock_aws_client)
        
        # Mock EC2 client
        mock_ec2 = Mock()
        mock_aws_client.get_ec2_client.return_value = mock_ec2
        
        # Return sample instances
        raw_instances = [sample_data["instances"][0]]
        raw_instances[0]["LaunchTime"] = datetime(2025, 6, 1)
        
        mock_ec2.get_paginator.return_value.paginate.return_value = [
            {"Reservations": [{"Instances": raw_instances}]}
        ]
        
        # Collect with exclude filter
        instances = collector._collect_region_instances(
            "us-east-1",
            exclude_tags=[("Environment", "development")],
        )
        
        # Should be excluded
        assert len(instances) == 0


class TestCloudWatchCollector:
    """Tests for CloudWatchCollector."""
    
    def test_process_datapoints(self, mock_aws_client):
        """Test datapoint processing."""
        collector = CloudWatchCollector(mock_aws_client)
        
        now = datetime.utcnow()
        datapoints = [
            {"Timestamp": now - timedelta(hours=2), "Average": 20.0, "Maximum": 30.0},
            {"Timestamp": now - timedelta(hours=1), "Average": 25.0, "Maximum": 35.0},
            {"Timestamp": now, "Average": 22.0, "Maximum": 32.0},
        ]
        
        result = collector._process_datapoints(datapoints, ["Average", "Maximum"])
        
        assert result["datapoint_count"] == 3
        assert result["average"] == pytest.approx(22.33, rel=0.1)  # Mean of 20, 25, 22
        assert "raw_values" in result
    
    def test_empty_datapoints(self, mock_aws_client):
        """Test handling of empty datapoints."""
        collector = CloudWatchCollector(mock_aws_client)
        
        result = collector._process_datapoints([], ["Average"])
        
        assert result["datapoint_count"] == 0
        assert result["average"] == 0
    
    def test_percentile_calculation(self, mock_aws_client):
        """Test percentile calculation."""
        collector = CloudWatchCollector(mock_aws_client)
        
        # Test with known values
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        p50 = collector._percentile(values, 50)
        assert p50 == pytest.approx(5.5, rel=0.1)
        
        p95 = collector._percentile(values, 95)
        assert p95 == pytest.approx(9.55, rel=0.1)
        
        p99 = collector._percentile(values, 99)
        assert p99 == pytest.approx(9.91, rel=0.1)
    
    def test_merge_idle_periods(self, mock_aws_client):
        """Test merging of consecutive idle hours."""
        collector = CloudWatchCollector(mock_aws_client)
        
        # Test consecutive hours
        idle_hours = [
            {"hour": 22, "average_cpu": 2.0, "idle_ratio": 0.9},
            {"hour": 23, "average_cpu": 1.5, "idle_ratio": 0.95},
            {"hour": 0, "average_cpu": 1.0, "idle_ratio": 0.98},
            {"hour": 1, "average_cpu": 1.2, "idle_ratio": 0.96},
            {"hour": 2, "average_cpu": 0.8, "idle_ratio": 0.99},
            {"hour": 3, "average_cpu": 0.9, "idle_ratio": 0.98},
        ]
        
        windows = collector._merge_idle_periods(idle_hours)
        
        # Should merge into one 6-hour window
        assert len(windows) == 1
        assert windows[0]["duration_hours"] == 6
    
    def test_get_usage_summary(self, mock_aws_client):
        """Test usage summary generation."""
        collector = CloudWatchCollector(mock_aws_client)
        
        metrics = {
            "CPUUtilization": {
                "average": 15.0,
                "maximum": 45.0,
                "p95": 35.0,
                "p99": 42.0,
                "datapoint_count": 8640,
            }
        }
        
        summary = collector.get_usage_summary(metrics)
        
        assert summary["cpu_average"] == 15.0
        assert summary["cpu_p95"] == 35.0
        assert summary["is_underutilized"] is True  # p95 < 40
        assert summary["is_idle"] is False  # average >= 5
        assert summary["datapoints_available"] == 8640


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

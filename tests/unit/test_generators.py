"""Unit tests for generators."""

import pytest
import json
from pathlib import Path
from datetime import datetime

from cli.generators.terraform_generator import TerraformGenerator
from cli.generators.report_generator import ReportGenerator
from cli.analyzers.rightsizing_analyzer import RightsizingRecommendation


@pytest.fixture
def sample_recommendations():
    """Create sample recommendations for testing."""
    return [
        RightsizingRecommendation(
            instance_id="i-0abc123def456789a",
            instance_name="web-server-1",
            region="us-east-1",
            current_type="t3.xlarge",
            recommended_type="t3.large",
            confidence="high",
            confidence_reasons=["Very low CPU utilization", "Stable workload"],
            current_monthly_cost=121.47,
            recommended_monthly_cost=60.74,
            monthly_savings=60.73,
            annual_savings=728.76,
            savings_percentage=50.0,
            cpu_average=15.2,
            cpu_p95=28.5,
            cpu_max=52.3,
            is_production=False,
            is_database=False,
            data_days=30,
        ),
        RightsizingRecommendation(
            instance_id="i-0bcd234efa567890b",
            instance_name="api-server-1",
            region="us-east-1",
            current_type="m5.2xlarge",
            recommended_type="m5.xlarge",
            confidence="medium",
            confidence_reasons=["Low CPU utilization", "Some variation"],
            current_monthly_cost=280.32,
            recommended_monthly_cost=140.16,
            monthly_savings=140.16,
            annual_savings=1681.92,
            savings_percentage=50.0,
            cpu_average=8.5,
            cpu_p95=18.3,
            cpu_max=32.1,
            is_production=False,
            is_database=False,
            data_days=30,
        ),
    ]


class TestTerraformGenerator:
    """Tests for TerraformGenerator."""
    
    def test_generate_rightsizing_tf(self, sample_recommendations):
        """Test Terraform file generation."""
        generator = TerraformGenerator()
        
        files = generator.generate_rightsizing_tf(
            sample_recommendations,
            region="us-east-1",
            profile="default",
        )
        
        # Check all expected files are generated
        assert "provider.tf" in files
        assert "variables.tf" in files
        assert "main.tf" in files
        assert "rollback.sh" in files
        assert "terraform.tfvars" in files
        assert "README.md" in files
    
    def test_provider_tf_content(self, sample_recommendations):
        """Test provider.tf content."""
        generator = TerraformGenerator()
        files = generator.generate_rightsizing_tf(sample_recommendations)
        
        provider = files["provider.tf"]
        
        assert "terraform {" in provider
        assert "required_version" in provider
        assert "hashicorp/aws" in provider
        assert "provider \"aws\"" in provider
    
    def test_variables_tf_content(self, sample_recommendations):
        """Test variables.tf content."""
        generator = TerraformGenerator()
        files = generator.generate_rightsizing_tf(sample_recommendations)
        
        variables = files["variables.tf"]
        
        assert "variable \"aws_region\"" in variables
        assert "variable \"aws_profile\"" in variables
        # Check for instance-specific variables
        assert "apply_i_0abc123def456789a" in variables
        assert "apply_i_0bcd234efa567890b" in variables
    
    def test_main_tf_contains_recommendations(self, sample_recommendations):
        """Test main.tf contains all recommendations."""
        generator = TerraformGenerator()
        files = generator.generate_rightsizing_tf(sample_recommendations)
        
        main = files["main.tf"]
        
        # Check each recommendation is included
        assert "i-0abc123def456789a" in main
        assert "i-0bcd234efa567890b" in main
        assert "t3.xlarge" in main
        assert "t3.large" in main
        assert "m5.2xlarge" in main
        assert "m5.xlarge" in main
    
    def test_rollback_script_content(self, sample_recommendations):
        """Test rollback.sh content."""
        generator = TerraformGenerator()
        files = generator.generate_rightsizing_tf(sample_recommendations)
        
        rollback = files["rollback.sh"]
        
        assert "#!/bin/bash" in rollback
        assert "i-0abc123def456789a" in rollback
        assert "t3.xlarge" in rollback  # Original type for rollback
        assert "aws ec2 stop-instances" in rollback
        assert "aws ec2 modify-instance-attribute" in rollback
        assert "aws ec2 start-instances" in rollback
    
    def test_tfvars_content(self, sample_recommendations):
        """Test terraform.tfvars content."""
        generator = TerraformGenerator()
        files = generator.generate_rightsizing_tf(
            sample_recommendations,
            region="us-west-2",
            profile="production",
        )
        
        tfvars = files["terraform.tfvars"]
        
        assert 'aws_region  = "us-west-2"' in tfvars
        assert 'aws_profile = "production"' in tfvars
        assert "apply_i_0abc123def456789a = true" in tfvars
    
    def test_write_files(self, sample_recommendations, tmp_path):
        """Test writing files to disk."""
        generator = TerraformGenerator()
        files = generator.generate_rightsizing_tf(sample_recommendations)
        
        output_dir = generator.write_files(files, str(tmp_path))
        
        # Verify files exist
        assert (output_dir / "provider.tf").exists()
        assert (output_dir / "main.tf").exists()
        assert (output_dir / "variables.tf").exists()
        assert (output_dir / "rollback.sh").exists()
        assert (output_dir / "README.md").exists()


class TestReportGenerator:
    """Tests for ReportGenerator."""
    
    def test_calculate_summary(self, sample_recommendations):
        """Test summary calculation."""
        generator = ReportGenerator()
        
        # Convert to dicts
        recs_data = [r.to_dict() for r in sample_recommendations]
        
        summary = generator._calculate_summary(recs_data, instances_analyzed=100)
        
        assert summary["total_recommendations"] == 2
        assert summary["instances_analyzed"] == 100
        assert summary["total_monthly_savings"] == pytest.approx(200.89, rel=0.1)
        assert summary["high_confidence_count"] == 1
        assert summary["medium_confidence_count"] == 1
    
    def test_generate_html_report(self, sample_recommendations):
        """Test HTML report generation."""
        generator = ReportGenerator()
        
        content = generator.generate_report(
            sample_recommendations,
            instances_analyzed=100,
            format_type="html",
        )
        
        assert "<!DOCTYPE html>" in content
        assert "Cloud Cost Slayer" in content
        assert "i-0abc123def456789a" in content
        assert "$60.73" in content or "60.73" in content
    
    def test_generate_json_report(self, sample_recommendations):
        """Test JSON report generation."""
        generator = ReportGenerator()
        
        content = generator.generate_report(
            sample_recommendations,
            instances_analyzed=100,
            format_type="json",
        )
        
        # Should be valid JSON
        data = json.loads(content)
        
        assert "summary" in data
        assert "recommendations" in data
        assert data["summary"]["total_recommendations"] == 2
    
    def test_generate_markdown_report(self, sample_recommendations):
        """Test Markdown report generation."""
        generator = ReportGenerator()
        
        content = generator.generate_report(
            sample_recommendations,
            instances_analyzed=100,
            format_type="markdown",
        )
        
        assert "# Cloud Cost Slayer" in content
        assert "## Executive Summary" in content
        assert "| Instance |" in content
    
    def test_generate_table_report(self, sample_recommendations):
        """Test table report generation."""
        generator = ReportGenerator()
        
        content = generator.generate_report(
            sample_recommendations,
            instances_analyzed=100,
            format_type="table",
        )
        
        assert "Cloud Cost Slayer" in content
        assert "SUMMARY" in content
        assert "Recommendations:" in content
    
    def test_write_to_file(self, sample_recommendations, tmp_path):
        """Test writing report to file."""
        generator = ReportGenerator()
        
        output_path = tmp_path / "report.html"
        
        content = generator.generate_report(
            sample_recommendations,
            instances_analyzed=100,
            format_type="html",
            output_path=str(output_path),
        )
        
        assert output_path.exists()
        assert output_path.read_text() == content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

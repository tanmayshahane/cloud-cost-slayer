"""
Terraform Configuration Generator.

Generates Terraform files for implementing recommendations:
- Right-sizing changes
- Variable files
- Provider configuration
- Rollback scripts
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from jinja2 import Template

from ..utils.logger import get_logger

logger = get_logger(__name__)


# Templates directory - relative to this file
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_template(filename: str) -> str:
    """
    Load a template file from the templates directory.
    
    Args:
        filename: Name of the template file (e.g., 'provider.tf')
        
    Returns:
        Template content as string
        
    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_path = TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


class TerraformGenerator:
    """
    Generate Terraform configurations for implementing recommendations.
    
    Creates complete Terraform projects with:
    - Provider configuration
    - Variable definitions
    - Resource changes
    - Rollback scripts
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize Terraform generator.
        
        Args:
            output_dir: Directory to write Terraform files
        """
        self.output_dir = Path(output_dir or "./terraform-output")
        self._env = None
    
    def generate_rightsizing_tf(
        self,
        recommendations: list,
        region: str = "us-east-1",
        profile: str = "default",
    ) -> dict[str, str]:
        """
        Generate Terraform files for rightsizing recommendations.
        
        Args:
            recommendations: List of RightsizingRecommendation objects
            region: Default AWS region
            profile: Default AWS profile
        
        Returns:
            Dictionary mapping filename to content
        """
        timestamp = datetime.now().isoformat()
        
        # Convert recommendations to dicts if needed
        recs_data = [
            r.to_dict() if hasattr(r, "to_dict") else r
            for r in recommendations
        ]
        
        total_savings = sum(r.get("monthly_savings", 0) for r in recs_data)
        
        # Render templates
        context = {
            "timestamp": timestamp,
            "recommendations": recs_data,
            "total_savings": round(total_savings, 2),
            "default_region": region,
            "default_profile": profile,
        }
        
        files = {
            "provider.tf": self._render_template_file("provider.tf", context),
            "variables.tf": self._render_template_file("variables.tf", context),
            "main.tf": self._render_template_file("rightsizing.tf", context),
            "rollback.sh": self._render_template_file("rollback.sh", context),
        }
        
        # Add tfvars with defaults
        tfvars = self._generate_tfvars(recs_data, region, profile)
        files["terraform.tfvars"] = tfvars
        
        # Add README
        files["README.md"] = self._generate_readme(recs_data, total_savings)
        
        return files
    
    def _render_template(self, template: str, context: dict) -> str:
        """Render a Jinja2 template string."""
        from jinja2 import Template
        tmpl = Template(template)
        return tmpl.render(**context)
    
    def _render_template_file(self, template_filename: str, context: dict) -> str:
        """Load and render a Jinja2 template from file."""
        from jinja2 import Template
        template_content = _load_template(template_filename)
        tmpl = Template(template_content)
        return tmpl.render(**context)
    
    def _generate_tfvars(
        self,
        recommendations: list[dict],
        region: str,
        profile: str,
    ) -> str:
        """Generate terraform.tfvars file."""
        lines = [
            "# Cloud Cost Slayer - Terraform Variables",
            f"# Generated: {datetime.now().isoformat()}",
            "",
            f'aws_region  = "{region}"',
            f'aws_profile = "{profile}"',
            "",
            "# Set to false to skip specific instances:",
        ]
        
        for rec in recommendations:
            instance_id = rec["instance_id"].replace("-", "_")
            lines.append(f'apply_{instance_id} = true')
        
        return "\n".join(lines)
    
    def _generate_readme(
        self,
        recommendations: list[dict],
        total_savings: float,
    ) -> str:
        """Generate README for Terraform directory."""
        return f"""# Cloud Cost Slayer - Terraform Configuration

Generated: {datetime.now().isoformat()}

## Summary

This Terraform configuration implements {len(recommendations)} rightsizing recommendations
with an estimated monthly savings of **${total_savings:.2f}**.

## Recommendations

| Instance | Current | Recommended | Monthly Savings | Confidence |
|----------|---------|-------------|-----------------|------------|
""" + "\n".join([
    f"| {r['instance_id']} | {r['current_type']} | {r['recommended_type']} | ${r['monthly_savings']:.2f} | {r['confidence']} |"
    for r in recommendations
]) + f"""

## Usage

1. **Review the changes**:
   ```bash
   terraform init
   terraform plan
   ```

2. **Apply changes**:
   ```bash
   terraform apply
   ```

3. **Rollback if needed**:
   ```bash
   bash rollback.sh
   ```

## Configuration

Edit `terraform.tfvars` to enable/disable specific instances:

```hcl
# Set to false to skip an instance
apply_i_abc123 = false
```

## Safety Notes

- All changes involve stopping instances briefly (30-60 seconds)
- Instances are automatically restarted after resize
- Keep the rollback.sh script handy for quick recovery
- Test in non-production environments first

## Estimated Savings

- Monthly: **${total_savings:.2f}**
- Annual: **${total_savings * 12:.2f}**
"""
    
    def write_files(
        self,
        files: dict[str, str],
        output_dir: Optional[str] = None,
    ) -> Path:
        """
        Write generated files to disk.
        
        Args:
            files: Dictionary mapping filename to content
            output_dir: Output directory (uses default if not specified)
        
        Returns:
            Path to output directory
        """
        output_path = Path(output_dir) if output_dir else self.output_dir
        output_path.mkdir(parents=True, exist_ok=True)
        
        for filename, content in files.items():
            file_path = output_path / filename
            file_path.write_text(content)
            logger.debug(f"Wrote {file_path}")
        
        # Make rollback script executable
        rollback_path = output_path / "rollback.sh"
        if rollback_path.exists():
            os.chmod(rollback_path, 0o755)
        
        logger.info(f"Terraform files written to {output_path}")
        return output_path
    
    def generate_and_write(
        self,
        recommendations: list,
        output_dir: Optional[str] = None,
        region: str = "us-east-1",
        profile: str = "default",
    ) -> Path:
        """
        Generate and write Terraform files in one step.
        
        Args:
            recommendations: List of recommendations
            output_dir: Output directory
            region: Default AWS region
            profile: Default AWS profile
        
        Returns:
            Path to output directory
        """
        files = self.generate_rightsizing_tf(recommendations, region, profile)
        return self.write_files(files, output_dir)

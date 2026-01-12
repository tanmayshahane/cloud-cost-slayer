"""
Report Generator.

Generates reports in multiple formats:
- HTML executive summary
- JSON data export
- Markdown reports
- Console tables
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


# Templates directory - relative to this file
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_template(filename: str) -> str:
    """
    Load a template file from the templates directory.
    
    Args:
        filename: Name of the template file (e.g., 'report.html')
        
    Returns:
        Template content as string
        
    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_path = TEMPLATES_DIR / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return template_path.read_text(encoding="utf-8")


class ReportGenerator:
    """
    Generate cost optimization reports in multiple formats.
    
    Supports HTML, JSON, Markdown, and console table output.
    """
    
    def __init__(self):
        """Initialize report generator."""
        pass
    
    def generate_report(
        self,
        recommendations: list,
        instances_analyzed: int = 0,
        format_type: str = "html",
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate a report in the specified format.
        
        Args:
            recommendations: List of recommendation objects
            instances_analyzed: Total instances analyzed
            format_type: Output format (html, json, markdown, table)
            output_path: Optional path to write the report
        
        Returns:
            Report content as string
        """
        # Convert to dicts if needed
        recs_data = [
            r.to_dict() if hasattr(r, "to_dict") else r
            for r in recommendations
        ]
        
        # Calculate summary
        summary = self._calculate_summary(recs_data, instances_analyzed)
        
        # Generate based on format
        if format_type == "json":
            content = self._generate_json(recs_data, summary)
        elif format_type == "markdown":
            content = self._generate_markdown(recs_data, summary)
        elif format_type == "table":
            content = self._generate_table(recs_data, summary)
        else:  # html
            content = self._generate_html(recs_data, summary)
        
        # Write to file if path specified
        if output_path:
            Path(output_path).write_text(content)
            logger.info(f"Report written to {output_path}")
        
        return content
    
    def _calculate_summary(
        self,
        recommendations: list[dict],
        instances_analyzed: int,
    ) -> dict:
        """Calculate summary statistics."""
        total_monthly = sum(r.get("monthly_savings", 0) for r in recommendations)
        
        high_recs = [r for r in recommendations if r.get("confidence") == "high"]
        medium_recs = [r for r in recommendations if r.get("confidence") == "medium"]
        low_recs = [r for r in recommendations if r.get("confidence") == "low"]
        
        return {
            "total_recommendations": len(recommendations),
            "instances_analyzed": instances_analyzed,
            "total_monthly_savings": round(total_monthly, 2),
            "total_annual_savings": round(total_monthly * 12, 2),
            "high_confidence_count": len(high_recs),
            "high_confidence_savings": round(sum(r.get("monthly_savings", 0) for r in high_recs), 2),
            "medium_confidence_count": len(medium_recs),
            "medium_confidence_savings": round(sum(r.get("monthly_savings", 0) for r in medium_recs), 2),
            "low_confidence_count": len(low_recs),
            "low_confidence_savings": round(sum(r.get("monthly_savings", 0) for r in low_recs), 2),
        }
    
    def _generate_html(self, recommendations: list[dict], summary: dict) -> str:
        """Generate HTML report from template file."""
        from jinja2 import Template
        
        template_content = _load_template("report.html")
        template = Template(template_content)
        return template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            summary=summary,
            recommendations=recommendations[:50],  # Limit to top 50
        )
    
    def _generate_markdown(self, recommendations: list[dict], summary: dict) -> str:
        """Generate Markdown report from template file."""
        from jinja2 import Template
        
        template_content = _load_template("report.md")
        template = Template(template_content)
        return template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            summary=summary,
            recommendations=recommendations[:50],
        )
    
    def _generate_json(self, recommendations: list[dict], summary: dict) -> str:
        """Generate JSON report."""
        return json.dumps({
            "generated_at": datetime.now().isoformat(),
            "summary": summary,
            "recommendations": recommendations,
        }, indent=2)
    
    def _generate_table(self, recommendations: list[dict], summary: dict) -> str:
        """Generate plain text table report."""
        lines = [
            "=" * 80,
            "Cloud Cost Slayer - Optimization Report".center(80),
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(80),
            "=" * 80,
            "",
            "SUMMARY",
            "-" * 40,
            f"Total Monthly Savings: ${summary['total_monthly_savings']:,.2f}",
            f"Total Annual Savings:  ${summary['total_annual_savings']:,.2f}",
            f"Recommendations:       {summary['total_recommendations']}",
            f"Instances Analyzed:    {summary['instances_analyzed']}",
            "",
            "BY CONFIDENCE",
            "-" * 40,
            f"High:   {summary['high_confidence_count']:3d} recommendations (${summary['high_confidence_savings']:,.2f}/mo)",
            f"Medium: {summary['medium_confidence_count']:3d} recommendations (${summary['medium_confidence_savings']:,.2f}/mo)",
            f"Low:    {summary['low_confidence_count']:3d} recommendations (${summary['low_confidence_savings']:,.2f}/mo)",
            "",
            "TOP RECOMMENDATIONS",
            "-" * 80,
            f"{'Instance':<20} {'Current':<12} {'New':<12} {'Savings':>10} {'Conf':>8}",
            "-" * 80,
        ]
        
        for rec in recommendations[:20]:
            lines.append(
                f"{rec['instance_id']:<20} "
                f"{rec['current_type']:<12} "
                f"{rec['recommended_type']:<12} "
                f"${rec['monthly_savings']:>8.2f} "
                f"{rec['confidence'].upper():>8}"
            )
        
        lines.extend([
            "-" * 80,
            "",
            "Generated by Cloud Cost Slayer v0.1.0",
        ])
        
        return "\n".join(lines)

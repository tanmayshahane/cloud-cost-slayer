# Cloud Cost Slayer - Right-Sizing Changes
# Generated: {{ timestamp }}
# 
# This configuration will resize the following instances:
{% for rec in recommendations %}
# - {{ rec.instance_id }}: {{ rec.current_type }} -> {{ rec.recommended_type }} (saves ${{ rec.monthly_savings }}/month)
{% endfor %}
#
# Estimated Total Monthly Savings: ${{ total_savings }}
#
# IMPORTANT: Review carefully before applying!
# Run: terraform plan
# Apply: terraform apply

{% for rec in recommendations %}
# Instance: {{ rec.instance_id }}
# Name: {{ rec.instance_name }}
# Current Type: {{ rec.current_type }}
# Recommended: {{ rec.recommended_type }}
# Monthly Savings: ${{ rec.monthly_savings }}
# Confidence: {{ rec.confidence | upper }}

resource "null_resource" "resize_{{ rec.instance_id | replace("-", "_") }}" {
  count = var.apply_{{ rec.instance_id | replace("-", "_") }} ? 1 : 0

  provisioner "local-exec" {
    command = <<-EOT
      echo "Stopping instance {{ rec.instance_id }}..."
      aws ec2 stop-instances --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
      
      echo "Waiting for instance to stop..."
      aws ec2 wait instance-stopped --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
      
      echo "Modifying instance type to {{ rec.recommended_type }}..."
      aws ec2 modify-instance-attribute --instance-id {{ rec.instance_id }} --instance-type {{ rec.recommended_type }} --region {{ rec.region }}
      
      echo "Starting instance..."
      aws ec2 start-instances --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
      
      echo "Waiting for instance to start..."
      aws ec2 wait instance-running --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
      
      echo "Done! Instance {{ rec.instance_id }} is now {{ rec.recommended_type }}"
    EOT
  }

  triggers = {
    instance_type = "{{ rec.recommended_type }}"
    applied_at    = timestamp()
  }
}

{% endfor %}

# Output summary
output "recommendations_applied" {
  description = "Summary of applied changes"
  value = {
{% for rec in recommendations %}
    "{{ rec.instance_id }}" = {
      name           = "{{ rec.instance_name }}"
      original_type  = "{{ rec.current_type }}"
      new_type       = "{{ rec.recommended_type }}"
      monthly_savings = {{ rec.monthly_savings }}
      applied        = var.apply_{{ rec.instance_id | replace("-", "_") }}
    }
{% endfor %}
  }
}

output "total_monthly_savings" {
  description = "Total estimated monthly savings"
  value       = {{ total_savings }}
}

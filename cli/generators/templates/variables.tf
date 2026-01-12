# Cloud Cost Slayer - Variables
# Generated: {{ timestamp }}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "{{ default_region }}"
}

variable "aws_profile" {
  description = "AWS CLI profile"
  type        = string
  default     = "{{ default_profile }}"
}

{% for rec in recommendations %}
variable "apply_{{ rec.instance_id | replace("-", "_") }}" {
  description = "Apply rightsizing for {{ rec.instance_id }}"
  type        = bool
  default     = true
}
{% endfor %}

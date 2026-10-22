variable "subscription_id" {
  type        = string
  description = "Your Azure subscription ID."
}

variable "location" {
  type    = string
  default = "spaincentral"
}

variable "prefix" {
  type    = string
  default = "studentlab"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,15}$", var.prefix))
    error_message = "Use 3-16 lowercase letters/digits, starting with a letter."
  }
}

variable "registry_name" {
  type        = string
  description = "Globally unique ACR name, 5-50 lowercase letters/digits."
  validation {
    condition     = can(regex("^[a-z0-9]{5,50}$", var.registry_name))
    error_message = "ACR name must be 5-50 lowercase letters/digits."
  }
}

variable "admin_cidr" {
  type        = string
  description = "Your public IPv4 address followed by /32. Never 0.0.0.0/0."
  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && can(regex("^[0-9.]+/32$", var.admin_cidr)) && var.admin_cidr != "0.0.0.0/32"
    error_message = "Supply a valid single IPv4 /32, for example 203.0.113.10/32."
  }
}

variable "ssh_public_key" {
  type        = string
  description = "Public SSH key text. Never pass a private key."
  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) ", var.ssh_public_key))
    error_message = "Supply an ssh-ed25519 or ssh-rsa public key."
  }
}

variable "vm_size" {
  type        = string
  default     = "Standard_B2s"
  description = "2 vCPU / 4 GB lab baseline. Not guaranteed free; verify regional availability/pricing."
}

variable "k3s_version" {
  type    = string
  default = "v1.37.1+k3s1"
}

variable "runtime" {
  type        = string
  default     = "k3s"
  description = "Use compose for the coursework pipeline; k3s preserves the original Azure lab. Changing an existing VM can replace it."
  validation {
    condition     = contains(["k3s", "compose"], var.runtime)
    error_message = "Choose k3s or compose."
  }
}

variable "enable_course_tools" {
  type        = bool
  default     = false
  description = "Create the separate billable SonarQube/Nexus VM and its network."
}

variable "tools_vm_size" {
  type        = string
  default     = "Standard_D4s_v4"
  description = "4 vCPU / 16 GB tools baseline. Check student quota, regional availability and price before applying."
}

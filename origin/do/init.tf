terraform {

  required_version = ">= 1.6.3"

  backend "s3" {
    endpoints = {
      s3 = "https://nyc3.digitaloceanspaces.com"
    }

    bucket = "unifist-terraform-state"
    key    = "unifist/platform/unums/{{ unum }}/origins/discord"

    # Deactivate a few AWS-specific checks
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_s3_checksum            = true
    region                      = "us-east-1"
  }

  required_providers {
    digitalocean = {
      source = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
    kubernetes = {
      source = "hashicorp/kubernetes"
      version = "2.35.1"
    }
    kustomization = {
      source  = "kbst/kustomization"
      version = "0.9.0"
    }
  }
}

data "digitalocean_kubernetes_cluster" "cluster" {
  name = "do-{{ unum }}-unum"
}

provider "kubernetes" {
  host = data.digitalocean_kubernetes_cluster.cluster.endpoint

  cluster_ca_certificate = base64decode(
    data.digitalocean_kubernetes_cluster.cluster.kube_config[0].cluster_ca_certificate
  )

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "doctl"
    args = ["kubernetes", "cluster", "kubeconfig", "exec-credential",
    "--version=v1beta1", data.digitalocean_kubernetes_cluster.cluster.id]
  }
}

provider "kustomization" {
  kubeconfig_path = "~/.kube/config"
  context = "do-{{ unum }}-unum"
}

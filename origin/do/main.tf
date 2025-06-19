resource "kubernetes_namespace" "namespace" {
  metadata {
    name = "discord"
  }
}

resource "kubernetes_config_map_v1" "config" {
  metadata {
    namespace = kubernetes_namespace.namespace.metadata[0].name
    name      = "config"
  }

  data = {
    "unum.json" = jsonencode({
        "name"     = "{{ unum }}"
        "location" = "do"
    })
  }
}

data "kustomization_build" "argocd" {
  path = "argocd"
}

resource "kustomization_resource" "resoures0" {
  for_each = data.kustomization_build.argocd.ids_prio[0]

  manifest = data.kustomization_build.argocd.manifests[each.value]

  depends_on = [kubernetes_namespace.namespace]
}

resource "kustomization_resource" "resoures1" {
  for_each = data.kustomization_build.argocd.ids_prio[1]

  manifest = data.kustomization_build.argocd.manifests[each.value]

  depends_on = [kustomization_resource.resoures0]
}

resource "kustomization_resource" "resoures2" {
  for_each = data.kustomization_build.argocd.ids_prio[2]

  manifest = data.kustomization_build.argocd.manifests[each.value]

  depends_on = [kustomization_resource.resoures1]
}

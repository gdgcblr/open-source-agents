# Default demo target: production-core (EKS 1.28 → 1.30 deprecation scenario)

resource "aws_eks_cluster" "production-core" {
  name     = "production-core"
  role_arn = "arn:aws:iam::123456789012:role/eks-cluster-production"
  version  = "1.28"

  vpc_config {
    subnet_ids = ["subnet-prod-a", "subnet-prod-b", "subnet-prod-c"]
  }

  enabled_cluster_log_types = ["api", "audit"]
}

resource "aws_eks_addon" "production_vpc_cni" {
  cluster_name  = aws_eks_cluster.production-core.name
  addon_name    = "vpc-cni"
  addon_version = "v1.12.6-eksbuild.2"
}

resource "aws_eks_addon" "production_coredns" {
  cluster_name  = aws_eks_cluster.production-core.name
  addon_name    = "coredns"
  addon_version = "v1.10.1-eksbuild.4"
}

resource "aws_eks_addon" "production_kube_proxy" {
  cluster_name  = aws_eks_cluster.production-core.name
  addon_name    = "kube-proxy"
  addon_version = "v1.28.15-eksbuild.4"
}

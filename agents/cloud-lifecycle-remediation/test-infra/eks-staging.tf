# Secondary EKS example: staging cluster one minor behind recommended

resource "aws_eks_cluster" "staging-platform" {
  name     = "staging-platform"
  role_arn = "arn:aws:iam::123456789012:role/eks-cluster-staging"
  version  = "1.30"

  vpc_config {
    subnet_ids = ["subnet-stg-a", "subnet-stg-b"]
  }
}

resource "aws_eks_addon" "staging_vpc_cni" {
  cluster_name  = aws_eks_cluster.staging-platform.name
  addon_name    = "vpc-cni"
  addon_version = "v1.16.0-eksbuild.1"
}

resource "aws_eks_addon" "staging_coredns" {
  cluster_name  = aws_eks_cluster.staging-platform.name
  addon_name    = "coredns"
  addon_version = "v1.10.1-eksbuild.6"
}

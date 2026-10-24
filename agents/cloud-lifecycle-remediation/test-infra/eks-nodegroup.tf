# EKS managed node group instance type deprecation demo

resource "aws_eks_node_group" "production-workers" {
  cluster_name    = aws_eks_cluster.production-core.name
  node_group_name = "production-workers"
  node_role_arn   = "arn:aws:iam::123456789012:role/eks-node-group"
  subnet_ids      = ["subnet-prod-a", "subnet-prod-b"]

  instance_types = ["m5.large"]

  scaling_config {
    desired_size = 2
    max_size     = 4
    min_size     = 1
  }
}

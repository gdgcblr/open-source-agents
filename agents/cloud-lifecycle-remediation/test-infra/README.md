# test-infra (demo Terraform)

Sample AWS Terraform layouts for the Cloud Lifecycle Remediation Agent. **Not wired to real AWS** — placeholders only.

## Layout

| File | Scenario |
|------|----------|
| `eks-production.tf` | EKS `production-core` at **1.28** + vpc-cni, coredns, kube-proxy |
| `eks-staging.tf` | EKS `staging-platform` at **1.29** + add-ons |
| `rds-postgres.tf` | Postgres **14.10**, deprecated **`db.r4.large`** + `postgres14` parameter group |
| `rds-mysql.tf` | MySQL **8.0.35** + `mysql8.0` parameter group |
| `ec2-app.tf` | EC2 **`m5.large`** (`api-server`) |
| `eks-nodegroup.tf` | Node group **`m5.large`** on `production-core` |

## Example agent events

**EKS (default demo):**

```bash
go run . '{"service":"EKS","resource_name":"production-core","current_version":"1.28","target_version":"1.30","eos_deadline":"2026-11-30","repo_dir":"./test-infra"}'
```

**EKS staging:**

```bash
go run . '{"service":"EKS","resource_name":"staging-platform","current_version":"1.29","target_version":"1.30","eos_deadline":"2026-12-15","repo_dir":"./test-infra"}'
```

**RDS Postgres:**

```bash
go run . '{"service":"RDS","resource_name":"analytics-db","current_version":"14","target_version":"16","eos_deadline":"2026-10-01","repo_dir":"./test-infra"}'
```

**RDS MySQL:**

```bash
go run . '{"service":"RDS","resource_name":"payments-ledger","current_version":"8.0.35","target_version":"8.0.39","eos_deadline":"2026-09-30","repo_dir":"./test-infra"}'
```

**RDS instance class (R4 → R6g):**

```bash
go run . '{"service":"RDS_INSTANCE","resource_name":"analytics-db","current_version":"db.r4.large","target_version":"db.r6g.large","eos_deadline":"2026-12-31","repo_dir":"./test-infra"}'
```

**EC2 instance type:**

```bash
go run . '{"service":"EC2","resource_name":"api-server","current_version":"m5.large","target_version":"m7i.large","eos_deadline":"2026-12-31","repo_dir":"./test-infra"}'
```

**EKS node group instance type:**

```bash
go run . '{"service":"EKS_NODEGROUP","resource_name":"production-workers","current_version":"m5.large","target_version":"m7i.large","eos_deadline":"2026-12-31","repo_dir":"./test-infra"}'
```

## Validate locally

Install Terraform if needed (Homebrew no longer ships `terraform` in core):

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

Then:

```bash
terraform -chdir=test-infra init -backend=false
terraform -chdir=test-infra validate
```

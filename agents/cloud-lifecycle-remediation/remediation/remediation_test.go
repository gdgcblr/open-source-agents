package remediation_test

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gdgcblr/open-source-agents/agents/cloud-lifecycle-remediation/remediation"
)

func TestScanAndPatchEKS(t *testing.T) {
	dir := t.TempDir()
	tf := filepath.Join(dir, "main.tf")
	content := `resource "aws_eks_cluster" "production-core" {
  name    = "production-core"
  version = "1.28"
}

resource "aws_eks_addon" "vpc_cni" {
  cluster_name  = aws_eks_cluster.production-core.name
  addon_name    = "vpc-cni"
  addon_version = "v1.12.6-eksbuild.2"
}
`
	if err := os.WriteFile(tf, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scan, err := remediation.ScanTerraformConfigs(context.Background(), remediation.ScanTerraformConfigsArgs{
		RepoDir:      dir,
		ResourceType: "aws_eks_cluster",
		ResourceName: "production-core",
	})
	if err != nil {
		t.Fatal(err)
	}
	if scan.Error != "" {
		t.Fatalf("scan error: %s", scan.Error)
	}
	if scan.CurrentVersion != "1.28" {
		t.Fatalf("got version %q", scan.CurrentVersion)
	}

	patch, err := remediation.PatchTerraformFile(context.Background(), remediation.PatchTerraformFileArgs{
		FilePath:       tf,
		TargetResource: "aws_eks_cluster.production-core",
		NewVersion:     "1.30",
		AssociatedUpdates: map[string]string{
			"aws_eks_addon.vpc_cni.addon_version": "v1.18.2-eksbuild.1",
		},
	})
	if err != nil || !patch.Success {
		t.Fatalf("patch failed: %+v err=%v", patch, err)
	}

	updated, _ := os.ReadFile(tf)
	if !strings.Contains(string(updated), `version = "1.30"`) {
		t.Fatalf("cluster version not updated: %s", updated)
	}
	if !strings.Contains(string(updated), `addon_version = "v1.18.2-eksbuild.1"`) {
		t.Fatalf("addon version not updated: %s", updated)
	}
}

func TestScanAndPatchRDSInstanceClass(t *testing.T) {
	dir := t.TempDir()
	tf := filepath.Join(dir, "rds.tf")
	content := `resource "aws_db_instance" "analytics-db" {
  engine         = "postgres"
  instance_class = "db.r4.large"
}
`
	if err := os.WriteFile(tf, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scan, err := remediation.ScanTerraformConfigs(context.Background(), remediation.ScanTerraformConfigsArgs{
		RepoDir:        dir,
		ResourceType:   "aws_db_instance",
		ResourceName:   "analytics-db",
		ValueAttribute: "instance_class",
	})
	if err != nil || scan.Error != "" || scan.CurrentVersion != "db.r4.large" {
		t.Fatalf("scan: %+v err=%v", scan, err)
	}

	patch, err := remediation.PatchTerraformFile(context.Background(), remediation.PatchTerraformFileArgs{
		FilePath:        tf,
		TargetResource:  "aws_db_instance.analytics-db",
		NewVersion:      "db.r6g.large",
		TargetAttribute: "instance_class",
	})
	if err != nil || !patch.Success {
		t.Fatalf("patch: %+v err=%v", patch, err)
	}
}

func TestFetchGuidanceRDSInstance(t *testing.T) {
	g, err := remediation.FetchVersionUpgradeGuidance(context.Background(), remediation.FetchVersionUpgradeGuidanceArgs{
		Service:     "RDS_INSTANCE",
		FromVersion: "db.r4.large",
		ToVersion:   "db.r6g.large",
	})
	if err != nil || len(g.BreakingChanges) == 0 {
		t.Fatalf("guidance: %+v err=%v", g, err)
	}
}

func TestFetchGuidanceEKS(t *testing.T) {
	g, err := remediation.FetchVersionUpgradeGuidance(context.Background(), remediation.FetchVersionUpgradeGuidanceArgs{
		Service:     "EKS",
		FromVersion: "1.28",
		ToVersion:   "1.30",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(g.RecommendedAddons) == 0 {
		t.Fatal("expected addon recommendations")
	}
}

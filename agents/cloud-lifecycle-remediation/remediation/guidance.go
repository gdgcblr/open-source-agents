package remediation

import (
	"context"
	"fmt"
	"strings"
)

type guidanceEntry struct {
	breakingChanges     []string
	recommendedAddons   map[string]string
	newParamGroupFamily string
	notes               string
}

var guidanceTable = map[string]guidanceEntry{
	"EKS:1.28:1.30": {
		breakingChanges: []string{
			"Kubernetes API removals: batch/v1beta1 CronJob and other v1beta1 APIs removed; migrate manifests to stable versions.",
			"EKS platform version bumps may require node AMI refresh before control plane upgrade completes.",
			"Verify admission webhooks and CRDs against Kubernetes 1.30 compatibility matrix.",
		},
		recommendedAddons: map[string]string{
			"vpc-cni": "v1.18.2-eksbuild.1",
			"coredns": "v1.11.1-eksbuild.9",
		},
		notes: "Upgrade control plane first, then node groups, then cluster add-ons. Run kubectl api-resources to detect deprecated APIs.",
	},
	"EKS:1.29:1.30": {
		breakingChanges: []string{
			"Review deprecated API usage with pluto or kubent before upgrade.",
		},
		recommendedAddons: map[string]string{
			"vpc-cni": "v1.18.2-eksbuild.1",
			"coredns": "v1.11.1-eksbuild.9",
		},
		notes: "Single minor version step; still validate add-on compatibility.",
	},
	"RDS:postgres:14:16": {
		breakingChanges: []string{
			"Major engine upgrade requires aws_db_parameter_group family change to postgres16.",
			"Review logical replication and extension compatibility (pglogical, postgis).",
			"Plan maintenance window; major upgrades can restart the instance.",
		},
		newParamGroupFamily: "postgres16",
		notes: "Create a new DB parameter group in the postgres16 family and associate it before or during the engine_version bump.",
	},
	"RDS:mysql:8.0.35:8.0.39": {
		breakingChanges: []string{
			"Minor MySQL upgrades may reset dynamic parameters; compare parameter group diffs.",
		},
		newParamGroupFamily: "mysql8.0",
		notes: "For minor MySQL bumps, parameter group family often stays mysql8.0.",
	},
	"RDS_INSTANCE:db.r4.large:db.r6g.large": {
		breakingChanges: []string{
			"Graviton (r6g) uses a different architecture; verify application ARM compatibility.",
			"Plan a maintenance window; instance class change requires brief failover/restart.",
			"Compare Performance Insights and max_connections after resize.",
		},
		notes: "Validate storage throughput and Multi-AZ behavior after moving off deprecated R4 classes.",
	},
	"EC2:m5.large:m7i.large": {
		breakingChanges: []string{
			"Confirm AMI and user-data scripts support the target instance family.",
			"Update Auto Scaling launch templates or mixed instances policy if applicable.",
		},
		notes: "Review CPU credits (if switching burst families) and ENI limits for the new type.",
	},
	"EKS_NODEGROUP:m5.large:m7i.large": {
		breakingChanges: []string{
			"Launch a new node group with m7i.large, cordon/drain old nodes, then remove the old group.",
			"Verify DaemonSets and PVC storage classes on new nodes.",
		},
		notes: "Control plane version and add-ons must remain compatible; update aws_eks_node_group instance_types.",
	},
}

// FetchVersionUpgradeGuidance returns known compatibility rules for supported upgrade paths.
func FetchVersionUpgradeGuidance(_ context.Context, args FetchVersionUpgradeGuidanceArgs) (FetchVersionUpgradeGuidanceResult, error) {
	service := strings.ToUpper(strings.TrimSpace(args.Service))
	from := strings.TrimSpace(args.FromVersion)
	to := strings.TrimSpace(args.ToVersion)

	if service == "" || from == "" || to == "" {
		return FetchVersionUpgradeGuidanceResult{}, fmt.Errorf("service, from_version, and to_version are required")
	}

	key := fmt.Sprintf("%s:%s:%s", service, from, to)
	if entry, ok := guidanceTable[key]; ok {
		return FetchVersionUpgradeGuidanceResult{
			BreakingChanges:     append([]string(nil), entry.breakingChanges...),
			RecommendedAddons:   copyMap(entry.recommendedAddons),
			NewParamGroupFamily: entry.newParamGroupFamily,
			Notes:               entry.notes,
		}, nil
	}

	if service == "RDS" {
		pgKey := fmt.Sprintf("RDS:postgres:%s:%s", from, to)
		if entry, ok := guidanceTable[pgKey]; ok {
			return FetchVersionUpgradeGuidanceResult{
				BreakingChanges:     append([]string(nil), entry.breakingChanges...),
				RecommendedAddons:   copyMap(entry.recommendedAddons),
				NewParamGroupFamily: entry.newParamGroupFamily,
				Notes:               entry.notes,
			}, nil
		}
	}

	return FetchVersionUpgradeGuidanceResult{
		BreakingChanges: []string{
			fmt.Sprintf("No curated guidance for %s %s -> %s; review AWS release notes manually.", service, from, to),
		},
		RecommendedAddons: map[string]string{},
		Notes:             "Extend guidanceTable in remediation/guidance.go for this upgrade path.",
	}, nil
}

func copyMap(in map[string]string) map[string]string {
	if in == nil {
		return map[string]string{}
	}
	out := make(map[string]string, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

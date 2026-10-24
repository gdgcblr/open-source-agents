package remediation

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ScanTerraformConfigs walks RepoDir for .tf files and locates the target resource and related blocks.
func ScanTerraformConfigs(_ context.Context, args ScanTerraformConfigsArgs) (ScanTerraformConfigsResult, error) {
	if args.RepoDir == "" || args.ResourceType == "" || args.ResourceName == "" {
		return ScanTerraformConfigsResult{
			Error: "repo_dir, resource_type, and resource_name are required",
		}, nil
	}

	info, err := os.Stat(args.RepoDir)
	if err != nil {
		return ScanTerraformConfigsResult{Error: err.Error()}, nil
	}
	if !info.IsDir() {
		return ScanTerraformConfigsResult{Error: "repo_dir is not a directory"}, nil
	}

	related := relatedResourceTypes(args.ResourceType)
	matched := make([]string, 0)
	currentVersion := ""

	err = filepath.WalkDir(args.RepoDir, func(path string, d os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if d.IsDir() || !strings.HasSuffix(d.Name(), ".tf") {
			return nil
		}

		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		content := string(data)

		if start, end, ok := findResourceBlock(content, args.ResourceType, args.ResourceName); ok {
			block := content[start:end]
			valueAttr := args.ValueAttribute
			if valueAttr == "" {
				valueAttr = defaultValueAttribute(args.ResourceType)
			}
			if v := extractPrimaryValue(block, valueAttr); v != "" {
				currentVersion = v
			}
			matched = append(matched, path)
		}

		if related != nil {
			for _, res := range listResources(content) {
				if related[res.Type] {
					if !contains(matched, path) {
						matched = append(matched, path)
					}
				}
			}
		}
		return nil
	})
	if err != nil {
		return ScanTerraformConfigsResult{Error: err.Error()}, nil
	}

	if len(matched) == 0 {
		return ScanTerraformConfigsResult{
			Error: fmt.Sprintf("no .tf files matched resource %q.%q under %s", args.ResourceType, args.ResourceName, args.RepoDir),
		}, nil
	}

	return ScanTerraformConfigsResult{
		MatchedFiles:   matched,
		CurrentVersion: currentVersion,
	}, nil
}

func defaultValueAttribute(resourceType string) string {
	switch resourceType {
	case "aws_db_instance":
		return "engine_version"
	case "aws_instance":
		return "instance_type"
	case "aws_eks_node_group":
		return "instance_types"
	default:
		return "version"
	}
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

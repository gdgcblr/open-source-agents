package remediation

import (
	"context"
	"fmt"
	"os"
	"strings"
)

// PatchTerraformFile updates version attributes and associated resource fields in place.
func PatchTerraformFile(_ context.Context, args PatchTerraformFileArgs) (PatchTerraformFileResult, error) {
	if args.FilePath == "" || args.TargetResource == "" || args.NewVersion == "" {
		return PatchTerraformFileResult{
			Error: "file_path, target_resource, and new_version are required",
		}, nil
	}

	before, err := os.ReadFile(args.FilePath)
	if err != nil {
		return PatchTerraformFileResult{Error: err.Error()}, nil
	}
	content := string(before)

	resourceType, resourceName, err := parseResourceAddress(args.TargetResource)
	if err != nil {
		return PatchTerraformFileResult{Error: err.Error()}, nil
	}

	start, end, ok := findResourceBlock(content, resourceType, resourceName)
	if !ok {
		return PatchTerraformFileResult{
			Error: fmt.Sprintf("resource block %s not found in %s", args.TargetResource, args.FilePath),
		}, nil
	}

	block := content[start:end]
	valueAttr := args.TargetAttribute
	if valueAttr == "" {
		valueAttr = defaultValueAttribute(resourceType)
	}
	updatedBlock, changed := setPrimaryValue(block, valueAttr, args.NewVersion)
	if !changed {
		return PatchTerraformFileResult{
			Error: fmt.Sprintf("attribute %s not found on %s", valueAttr, args.TargetResource),
		}, nil
	}
	content = content[:start] + updatedBlock + content[end:]

	for addrAttr, newVal := range args.AssociatedUpdates {
		parts := strings.SplitN(addrAttr, ".", 3)
		if len(parts) < 3 {
			return PatchTerraformFileResult{
				Error: fmt.Sprintf("associated update key %q must be type.name.attribute", addrAttr),
			}, nil
		}
		resType, resName, attr := parts[0], parts[1], parts[2]
		s, e, found := findResourceBlock(content, resType, resName)
		if !found {
			return PatchTerraformFileResult{
				Error: fmt.Sprintf("associated resource %s.%s not found", resType, resName),
			}, nil
		}
		sub := content[s:e]
		newSub, subChanged := setPrimaryValue(sub, attr, newVal)
		if !subChanged {
			return PatchTerraformFileResult{
				Error: fmt.Sprintf("attribute %s not found on %s.%s", attr, resType, resName),
			}, nil
		}
		content = content[:s] + newSub + content[e:]
	}

	if err := os.WriteFile(args.FilePath, []byte(content), 0o644); err != nil {
		return PatchTerraformFileResult{Error: err.Error()}, nil
	}

	return PatchTerraformFileResult{
		Success: true,
		Diff:    summarizeDiff(string(before), content, args.FilePath),
	}, nil
}

func summarizeDiff(before, after, path string) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Updated %s\n", path)
	for _, line := range strings.Split(after, "\n") {
		trim := strings.TrimSpace(line)
		if strings.Contains(trim, "version") || strings.Contains(trim, "engine_version") || strings.Contains(trim, "addon_version") || strings.Contains(trim, "family") || strings.Contains(trim, "instance_class") || strings.Contains(trim, "instance_type") || strings.Contains(trim, "instance_types") {
			fmt.Fprintf(&b, "  %s\n", strings.TrimRight(line, " "))
		}
	}
	if before == after {
		b.WriteString("  (no textual change detected)\n")
	}
	return b.String()
}

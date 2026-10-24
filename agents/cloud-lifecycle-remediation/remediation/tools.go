package remediation

import (
	"context"

	"google.golang.org/adk/v2/agent"
)

// ScanTerraformConfigsTool is the ADK function-tool entrypoint for repository scanning.
func ScanTerraformConfigsTool(_ agent.Context, args ScanTerraformConfigsArgs) (ScanTerraformConfigsResult, error) {
	return ScanTerraformConfigs(context.Background(), args)
}

// FetchVersionUpgradeGuidanceTool is the ADK function-tool entrypoint for upgrade guidance.
func FetchVersionUpgradeGuidanceTool(_ agent.Context, args FetchVersionUpgradeGuidanceArgs) (FetchVersionUpgradeGuidanceResult, error) {
	return FetchVersionUpgradeGuidance(context.Background(), args)
}

// PatchTerraformFileTool is the ADK function-tool entrypoint for HCL patching.
func PatchTerraformFileTool(_ agent.Context, args PatchTerraformFileArgs) (PatchTerraformFileResult, error) {
	return PatchTerraformFile(context.Background(), args)
}

// RunTerraformValidateTool is the ADK function-tool entrypoint for terraform fmt/validate.
func RunTerraformValidateTool(_ agent.Context, args RunTerraformValidateArgs) (RunTerraformValidateResult, error) {
	return RunTerraformValidate(context.Background(), args)
}

// CreateRemediationPRTool is the ADK function-tool entrypoint for git + GitHub PR creation.
func CreateRemediationPRTool(_ agent.Context, args CreateRemediationPRArgs) (CreateRemediationPRResult, error) {
	return CreateRemediationPR(context.Background(), args)
}

package remediation

// ScanTerraformConfigsArgs locates Terraform resources affected by a deprecation event.
type ScanTerraformConfigsArgs struct {
	RepoDir      string `json:"repo_dir" jsonschema:"Absolute or relative path to the Terraform repository root to scan."`
	ResourceType string `json:"resource_type" jsonschema:"Terraform resource type, e.g. aws_eks_cluster or aws_db_instance."`
	ResourceName     string `json:"resource_name" jsonschema:"Terraform resource block label (the name in quotes after the type)."`
	ValueAttribute   string `json:"value_attribute,omitempty" jsonschema:"Terraform attribute to read, e.g. version, engine_version, instance_class, instance_type, instance_types."`
}

// ScanTerraformConfigsResult summarizes files and the primary version attribute found.
type ScanTerraformConfigsResult struct {
	MatchedFiles   []string `json:"matched_files" jsonschema:"Paths to .tf files containing the target resource or related components."`
	CurrentVersion string   `json:"current_version" jsonschema:"Current value of the targeted attribute (version, engine_version, instance class/type, etc.)."`
	Error          string   `json:"error,omitempty" jsonschema:"Non-empty when the scan could not complete."`
}

// FetchVersionUpgradeGuidanceArgs requests compatibility notes for a version jump.
type FetchVersionUpgradeGuidanceArgs struct {
	Service     string `json:"service" jsonschema:"EKS, RDS, RDS_INSTANCE, EC2, or EKS_NODEGROUP."`
	FromVersion string `json:"from_version" jsonschema:"Currently deployed version."`
	ToVersion   string `json:"to_version" jsonschema:"Target version after remediation."`
}

// FetchVersionUpgradeGuidanceResult returns migration hints from a built-in lookup table.
type FetchVersionUpgradeGuidanceResult struct {
	BreakingChanges      []string          `json:"breaking_changes" jsonschema:"Notable breaking changes between versions."`
	RecommendedAddons    map[string]string `json:"recommended_addons" jsonschema:"For EKS: add-on name to recommended version."`
	NewParamGroupFamily  string            `json:"new_param_group_family" jsonschema:"For RDS: target DB parameter group family."`
	Notes                string            `json:"notes" jsonschema:"Additional migration notes."`
}

// PatchTerraformFileArgs applies version updates to a single Terraform file.
type PatchTerraformFileArgs struct {
	FilePath          string            `json:"file_path" jsonschema:"Path to the .tf file to patch."`
	TargetResource    string            `json:"target_resource" jsonschema:"Terraform address, e.g. aws_eks_cluster.production-core."`
	NewVersion        string            `json:"new_version" jsonschema:"New target value for the primary attribute (version, engine_version, instance class/type, etc.)."`
	TargetAttribute   string            `json:"target_attribute,omitempty" jsonschema:"Primary attribute to patch when not the default for the resource type."`
	AssociatedUpdates map[string]string `json:"associated_updates" jsonschema:"Map of terraform_address.attribute to new value, e.g. aws_eks_addon.vpc_cni.addon_version."`
}

// PatchTerraformFileResult reports patch outcome and a unified diff snippet.
type PatchTerraformFileResult struct {
	Success bool   `json:"success"`
	Diff    string `json:"diff"`
	Error   string `json:"error,omitempty"`
}

// RunTerraformValidateArgs runs fmt check and validate in a Terraform working directory.
type RunTerraformValidateArgs struct {
	WorkingDir string `json:"working_dir" jsonschema:"Directory containing Terraform configuration."`
}

// RunTerraformValidateResult captures validation output.
type RunTerraformValidateResult struct {
	Success bool   `json:"success"`
	Output  string `json:"output"`
}

// CreateRemediationPRArgs opens a draft pull request with patched Terraform changes.
type CreateRemediationPRArgs struct {
	RepoDir             string `json:"repo_dir" jsonschema:"Git repository root containing Terraform files."`
	BranchName          string `json:"branch_name" jsonschema:"New branch name; must not be main or master."`
	Title               string `json:"title" jsonschema:"Pull request title."`
	DescriptionMarkdown string `json:"description_markdown" jsonschema:"Pull request body in Markdown."`
}

// CreateRemediationPRResult returns the PR URL or an error message.
type CreateRemediationPRResult struct {
	PRURL string `json:"pr_url"`
	Error string `json:"error,omitempty"`
}

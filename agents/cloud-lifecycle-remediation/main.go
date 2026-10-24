package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/gdgcblr/open-source-agents/agents/cloud-lifecycle-remediation/remediation"
	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/agent/llmagent"
	"google.golang.org/adk/v2/runner"
	"google.golang.org/adk/v2/session"
	"google.golang.org/adk/v2/tool"
	"google.golang.org/adk/v2/tool/functiontool"
	"google.golang.org/genai"
)

const systemInstruction = `You are the Cloud Lifecycle Remediation Agent. Your job is to upgrade deprecated cloud infrastructure safely.

Protocol:
1. Inspect the incoming deprecation event JSON.
2. Call ScanTerraformConfigs with the correct resource_type and value_attribute (version, engine_version, instance_class, instance_type, or instance_types).
3. Call FetchVersionUpgradeGuidance using the event service (EKS, RDS, RDS_INSTANCE, EC2, EKS_NODEGROUP).
4. Call PatchTerraformFile with target_attribute when patching instance classes/types. Use AssociatedUpdates keys formatted as type.name.attribute (for example aws_eks_addon.vpc_cni.addon_version).
5. Call RunTerraformValidate on the repo directory. If validation fails, read the error output, repair with PatchTerraformFile, and validate again.
6. Call CreateRemediationPR on a bot branch only (for example bot/deprecations-eks-production-core). Never merge to main, never push to main/master, and never modify files outside the provided repo_dir.
7. Respond with a concise summary: modified attributes, validation status, migration checklist highlights, EoS deadline, and PR URL.

Safety guardrails:
- Do not delete unrelated resources.
- Do not edit branches named main or master.
- Prefer minimal diffs that only bump targeted lifecycle fields (versions, instance classes/types) and directly related add-on or parameter group fields.`

type deprecationEvent struct {
	Service        string `json:"service"`
	ResourceName   string `json:"resource_name"`
	CurrentVersion string `json:"current_version"`
	TargetVersion  string `json:"target_version"`
	EOSDeadline    string `json:"eos_deadline"`
	RepoDir        string `json:"repo_dir"`
}

func main() {
	loadDotEnvFromWorkingTree()

	ctx := context.Background()

	llm, modelName, err := newLLM(ctx)
	if err != nil {
		log.Fatalf("create model: %v", err)
	}
	log.Printf("Using model %q (LLM_PROVIDER=%s)", modelName, envOrDefault("LLM_PROVIDER", "auto"))

	tools, err := buildTools()
	if err != nil {
		log.Fatalf("build tools: %v", err)
	}

	remediationAgent, err := llmagent.New(llmagent.Config{
		Name:        "cloud_lifecycle_remediation_agent",
		Model:       llm,
		Description: "Autonomous agent that patches Terraform for AWS EKS/RDS version and instance-type deprecations.",
		Instruction: systemInstruction,
		Tools:       tools,
	})
	if err != nil {
		log.Fatalf("create agent: %v", err)
	}

	event := deprecationEvent{
		Service:        "EKS",
		ResourceName:   "production-core",
		CurrentVersion: "1.28",
		TargetVersion:  "1.30",
		EOSDeadline:    "2026-11-30",
		RepoDir:        "./test-infra",
	}
	if len(os.Args) > 1 && strings.TrimSpace(os.Args[1]) != "" {
		if err := json.Unmarshal([]byte(os.Args[1]), &event); err != nil {
			log.Fatalf("parse event JSON from argv[1]: %v", err)
		}
	}

	mapping, err := remediation.EventMappingForService(event.Service)
	if err != nil {
		log.Fatalf("event service: %v", err)
	}

	prompt := fmt.Sprintf(`Process this AWS deprecation remediation event and execute the full protocol:

`+"```json"+`
%s
`+"```"+`

Use resource_type %q and value_attribute %q when scanning.
Use service %q for FetchVersionUpgradeGuidance.
Set target_attribute %q on PatchTerraformFile for the primary resource.
Suggested branch: bot/deprecations-%s-%s.
Draft PR description must include:
- EoS deadline (%s)
- Migration checklist from guidance
- Summary of Terraform attribute changes
`, mustJSON(event), mapping.ResourceType, mapping.ValueAttribute, mapping.GuidanceService, mapping.ValueAttribute, strings.ToLower(event.Service), event.ResourceName, event.EOSDeadline)

	appName := "cloud-lifecycle-remediation"
	userID := "lifecycle-bot"
	sessionService := session.InMemoryService()
	sessionInstance, err := sessionService.Create(ctx, &session.CreateRequest{
		AppName: appName,
		UserID:  userID,
	})
	if err != nil {
		log.Fatalf("create session: %v", err)
	}

	r, err := runner.New(runner.Config{
		AppName:        appName,
		Agent:          remediationAgent,
		SessionService: sessionService,
	})
	if err != nil {
		log.Fatalf("create runner: %v", err)
	}

	input := genai.NewContentFromText(prompt, genai.RoleUser)
	events := r.Run(ctx, userID, sessionInstance.Session.ID(), input, agent.RunConfig{})

	fmt.Println("--- Cloud Lifecycle Remediation Agent ---")
	var final strings.Builder
	for ev, runErr := range events {
		if runErr != nil {
			log.Fatalf("agent run: %v", runErr)
		}
		if ev.Content == nil {
			continue
		}
		for _, part := range ev.Content.Parts {
			if part.Text != "" {
				fmt.Println(part.Text)
				final.WriteString(part.Text)
			}
		}
	}
	if final.Len() == 0 {
		log.Println("agent finished without textual response; check tool traces in ADK logs")
	}
}

func buildTools() ([]tool.Tool, error) {
	scanTool, err := functiontool.New(
		functiontool.Config{
			Name:        "ScanTerraformConfigs",
			Description: "Scans .tf files for a resource and extracts the targeted attribute (version, engine_version, instance_class, instance_type, instance_types) plus related files.",
		},
		remediation.ScanTerraformConfigsTool,
	)
	if err != nil {
		return nil, err
	}

	guidanceTool, err := functiontool.New(
		functiontool.Config{
			Name:        "FetchVersionUpgradeGuidance",
			Description: "Returns breaking changes, recommended EKS add-on versions, and RDS parameter group family shifts.",
		},
		remediation.FetchVersionUpgradeGuidanceTool,
	)
	if err != nil {
		return nil, err
	}

	patchTool, err := functiontool.New(
		functiontool.Config{
			Name:        "PatchTerraformFile",
			Description: "Patches version, engine_version, add-on, or parameter group attributes in a Terraform file.",
		},
		remediation.PatchTerraformFileTool,
	)
	if err != nil {
		return nil, err
	}

	validateTool, err := functiontool.New(
		functiontool.Config{
			Name:        "RunTerraformValidate",
			Description: "Runs terraform fmt and terraform validate in the working directory.",
		},
		remediation.RunTerraformValidateTool,
	)
	if err != nil {
		return nil, err
	}

	prTool, err := functiontool.New(
		functiontool.Config{
			Name:        "CreateRemediationPR",
			Description: "Creates an isolated git branch, commits .tf changes, pushes, and opens a draft GitHub pull request.",
		},
		remediation.CreateRemediationPRTool,
	)
	if err != nil {
		return nil, err
	}

	return []tool.Tool{scanTool, guidanceTool, patchTool, validateTool, prTool}, nil
}

func envOrDefault(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func mustJSON(v any) string {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		log.Fatalf("marshal event: %v", err)
	}
	return string(b)
}

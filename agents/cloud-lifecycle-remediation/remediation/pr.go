package remediation

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

var protectedBranches = map[string]bool{
	"main":   true,
	"master": true,
}

// CreateRemediationPR creates an isolated branch, commits .tf changes, pushes, and opens a draft PR.
func CreateRemediationPR(ctx context.Context, args CreateRemediationPRArgs) (CreateRemediationPRResult, error) {
	if args.RepoDir == "" || args.BranchName == "" {
		return CreateRemediationPRResult{Error: "repo_dir and branch_name are required"}, nil
	}
	if protectedBranches[strings.ToLower(args.BranchName)] {
		return CreateRemediationPRResult{Error: "refusing to use protected branch name main/master"}, nil
	}
	if strings.HasPrefix(args.BranchName, "refs/heads/main") || strings.HasPrefix(args.BranchName, "refs/heads/master") {
		return CreateRemediationPRResult{Error: "refusing to push to protected refs"}, nil
	}

	repoDir, err := filepath.Abs(args.RepoDir)
	if err != nil {
		return CreateRemediationPRResult{Error: err.Error()}, nil
	}

	if err := ensureGitRepo(ctx, repoDir); err != nil {
		return CreateRemediationPRResult{Error: err.Error()}, nil
	}

	currentBranch, err := gitOutput(ctx, repoDir, "rev-parse", "--abbrev-ref", "HEAD")
	if err != nil {
		return CreateRemediationPRResult{Error: fmt.Sprintf("git rev-parse: %v", err)}, nil
	}
	if protectedBranches[strings.ToLower(strings.TrimSpace(currentBranch))] {
		// Safe: we only commit on a new bot branch, never commit directly on main in normal flow.
	}

	if err := gitRun(ctx, repoDir, "checkout", "-b", args.BranchName); err != nil {
		if !strings.Contains(err.Error(), "already exists") {
			return CreateRemediationPRResult{Error: fmt.Sprintf("git checkout -b: %v", err)}, nil
		}
		if err := gitRun(ctx, repoDir, "checkout", args.BranchName); err != nil {
			return CreateRemediationPRResult{Error: fmt.Sprintf("git checkout: %v", err)}, nil
		}
	}

	if err := gitRun(ctx, repoDir, "add", "*.tf"); err != nil {
		return CreateRemediationPRResult{Error: fmt.Sprintf("git add: %v", err)}, nil
	}

	status, err := gitOutput(ctx, repoDir, "status", "--porcelain")
	if err != nil {
		return CreateRemediationPRResult{Error: err.Error()}, nil
	}
	if strings.TrimSpace(status) == "" {
		return CreateRemediationPRResult{Error: "no terraform changes to commit"}, nil
	}

	commitMsg := args.Title
	if commitMsg == "" {
		commitMsg = "chore(terraform): cloud lifecycle remediation"
	}
	if err := gitRun(ctx, repoDir, "commit", "-m", commitMsg); err != nil {
		return CreateRemediationPRResult{Error: fmt.Sprintf("git commit: %v", err)}, nil
	}

	if simulate := os.Getenv("SIMULATE_PR"); simulate == "1" || simulate == "true" {
		return CreateRemediationPRResult{
			PRURL: fmt.Sprintf("https://github.example.com/org/infra/pull/simulated-%s", sanitizeBranch(args.BranchName)),
		}, nil
	}

	if err := gitRun(ctx, repoDir, "push", "-u", "origin", args.BranchName); err != nil {
		return CreateRemediationPRResult{
			Error: fmt.Sprintf("git push failed (set SIMULATE_PR=true for offline demo): %v", err),
		}, nil
	}

	if _, err := exec.LookPath("gh"); err != nil {
		return CreateRemediationPRResult{
			Error: "gh CLI not found; install GitHub CLI or set SIMULATE_PR=true",
		}, nil
	}

	title := args.Title
	if title == "" {
		title = "Cloud lifecycle remediation"
	}
	body := args.DescriptionMarkdown
	if body == "" {
		body = "Automated Terraform remediation for cloud version deprecation."
	}

	prOut, err := gitCmd(ctx, repoDir, "gh", "pr", "create", "--draft", "--title", title, "--body", body, "--head", args.BranchName)
	if err != nil {
		return CreateRemediationPRResult{Error: fmt.Sprintf("gh pr create: %v\n%s", err, prOut)}, nil
	}

	return CreateRemediationPRResult{PRURL: strings.TrimSpace(prOut)}, nil
}

func ensureGitRepo(ctx context.Context, dir string) error {
	if _, err := os.Stat(filepath.Join(dir, ".git")); err == nil {
		return nil
	}
	if err := gitRun(ctx, dir, "init", "-b", "main"); err != nil {
		return err
	}
	if err := gitRun(ctx, dir, "add", "."); err != nil {
		return err
	}
	return gitRun(ctx, dir, "commit", "-m", "chore: seed terraform demo config")
}

func gitRun(ctx context.Context, dir string, args ...string) error {
	_, err := gitCmd(ctx, dir, "git", args...)
	return err
}

func gitOutput(ctx context.Context, dir string, args ...string) (string, error) {
	return gitCmd(ctx, dir, "git", args...)
}

func gitCmd(ctx context.Context, dir, bin string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.Dir = dir
	cmd.Env = os.Environ()
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	err := cmd.Run()
	return buf.String(), err
}

func sanitizeBranch(name string) string {
	return strings.NewReplacer("/", "-", " ", "-").Replace(name)
}

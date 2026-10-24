package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"

	"contribution-mentor/internal/config"
	"contribution-mentor/internal/mentor"
	"contribution-mentor/internal/web"
)

func main() {
	if err := config.LoadDotEnv(".env"); err != nil {
		fmt.Fprintf(os.Stderr, "load environment: %v\n", err)
		os.Exit(2)
	}

	repoPath := flag.String("repo", ".", "Path to the repository to inspect")
	question := flag.String("question", envOr("QUESTION", ""), "Question to ask the contribution mentor")
	webMode := flag.Bool("web", false, "Start the local web interface")
	webPort := flag.Int("port", 8080, "Port for the local web interface (bound to 127.0.0.1)")
	githubRepo := flag.String("github", envOr("GITHUB_REPO", ""), "GitHub repository in owner/name form")
	experience := flag.String("experience", envOr("EXPERIENCE", ""), "Your experience, skills, and preferred difficulty")
	issueNumber := flag.Int("issue", 0, "Plan a contribution for this open issue number")
	implementDefault, err := strconv.ParseBool(envOr("IMPLEMENT", "false"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "IMPLEMENT must be true or false: %v\n", err)
		os.Exit(2)
	}
	implement := flag.Bool("implement", implementDefault, "Propose changes for a selected issue and apply them only after confirmation")
	flag.Parse()

	if !*webMode && strings.TrimSpace(*githubRepo) == "" && strings.TrimSpace(*question) == "" {
		fmt.Fprintln(os.Stderr, "Provide a question with -question.")
		flag.Usage()
		os.Exit(2)
	}
	if *webMode && (*webPort < 1 || *webPort > 65535) {
		fmt.Fprintln(os.Stderr, "-port must be between 1 and 65535.")
		os.Exit(2)
	}
	if !*webMode {
		if strings.TrimSpace(*githubRepo) != "" && strings.TrimSpace(*experience) == "" {
			fmt.Fprintln(os.Stderr, "Provide your background with -experience when using -github.")
			flag.Usage()
			os.Exit(2)
		}
		if *issueNumber < 0 || (*issueNumber > 0 && strings.TrimSpace(*githubRepo) == "") {
			fmt.Fprintln(os.Stderr, "-issue requires -github and must be a positive issue number.")
			os.Exit(2)
		}
		if *implement && (*issueNumber == 0 || strings.TrimSpace(*githubRepo) == "") {
			fmt.Fprintln(os.Stderr, "IMPLEMENT=true requires -github and a specific -issue number.")
			os.Exit(2)
		}
	}

	client, err := mentor.NewModelClient(mentor.ModelConfig{
		Provider: envOr("LLM_PROVIDER", ""),
		BaseURL:  envOr("LLM_BASE_URL", ""),
		Model:    envOr("LLM_MODEL", ""),
		APIKey:   envOr("LLM_API_KEY", ""),
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "configure model provider: %v\n", err)
		os.Exit(2)
	}
	if *webMode {
		address := net.JoinHostPort("127.0.0.1", strconv.Itoa(*webPort))
		fmt.Printf("Contribution Mentor web UI: http://%s\n", address)
		if err := web.Start(address, client); err != nil {
			fmt.Fprintf(os.Stderr, "serve web interface: %v\n", err)
			os.Exit(1)
		}
		return
	}

	repo, err := mentor.InspectRepository(*repoPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "inspect repository: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Repository: %s\nProvider: %s\nModel: %s\n", repo.Root, client.Config().Provider, client.Config().Model)
	fmt.Println("Sending selected repository files to the configured model provider...")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	var answer string
	if strings.TrimSpace(*githubRepo) != "" {
		githubClient := mentor.NewGitHubClient()
		if *issueNumber > 0 {
			issue, err := githubClient.GetIssue(ctx, *githubRepo, *issueNumber)
			if err != nil {
				fmt.Fprintf(os.Stderr, "fetch GitHub issue: %v\n", err)
				os.Exit(1)
			}
			fmt.Printf("Selected issue: #%d %s\n%s\n", issue.Number, issue.Title, issue.HTMLURL)
			if *implement {
				changes, err := client.GenerateIssueChanges(ctx, *experience, issue, repo)
				if err != nil {
					fmt.Fprintf(os.Stderr, "generate proposed changes: %v\n", err)
					os.Exit(1)
				}
				applied, err := mentor.ApplyApprovedIssueChanges(repo, changes, os.Stdin, os.Stdout)
				if err != nil {
					fmt.Fprintf(os.Stderr, "apply proposed changes: %v\n", err)
					os.Exit(1)
				}
				if applied {
					fmt.Println("\nApproved changes applied. Review the files and run the project's tests before submitting.")
				} else {
					fmt.Println("\nCancelled; no files were changed.")
				}
				return
			}
			answer, err = client.PlanIssue(ctx, *experience, issue, repo)
		} else {
			issues, err := githubClient.ListOpenIssues(ctx, *githubRepo)
			if err != nil {
				fmt.Fprintf(os.Stderr, "fetch GitHub issues: %v\n", err)
				os.Exit(1)
			}
			if len(issues) == 0 {
				fmt.Fprintf(os.Stderr, "No open issues found in %s.\n", *githubRepo)
				os.Exit(1)
			}
			printIssues(issues)
			answer, err = client.RecommendIssues(ctx, *experience, issues, repo)
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "ask model provider: %v\n", err)
			os.Exit(1)
		}
	} else {
		answer, err = client.Ask(ctx, *question, repo)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ask model provider: %v\n", err)
			os.Exit(1)
		}
	}
	fmt.Println()
	fmt.Println(answer)
}

func printIssues(issues []mentor.GitHubIssue) {
	fmt.Println("\nOpen GitHub issues:")
	for _, issue := range issues {
		fmt.Printf("#%-5d %s\n       %s\n", issue.Number, issue.Title, issue.HTMLURL)
	}
	fmt.Println("\nMatching these issues to your experience...")
}

func envOr(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

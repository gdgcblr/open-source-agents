package mentor

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	githubAPIURL      = "https://api.github.com"
	maxGitHubIssues   = 20
	maxIssueBodySize  = 3000
	maxGitHubResponse = 4 * 1024 * 1024
)

var githubRepositoryPattern = regexp.MustCompile(`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`)

type GitHubIssue struct {
	Number   int    `json:"number"`
	Title    string `json:"title"`
	Body     string `json:"body"`
	HTMLURL  string `json:"html_url"`
	Comments int    `json:"comments"`
	State    string `json:"state"`
	Labels   []struct {
		Name string `json:"name"`
	} `json:"labels"`
	PullRequest json.RawMessage `json:"pull_request"`
}

type GitHubClient struct {
	baseURL string
	token   string
	http    *http.Client
}

func NewGitHubClient() *GitHubClient {
	return &GitHubClient{
		baseURL: githubAPIURL,
		token:   strings.TrimSpace(os.Getenv("GITHUB_TOKEN")),
		http:    &http.Client{Timeout: 20 * time.Second},
	}
}

func validateGitHubRepository(repository string) (string, string, error) {
	repository = strings.TrimSpace(repository)
	if !githubRepositoryPattern.MatchString(repository) {
		return "", "", fmt.Errorf("GitHub repository must be in owner/name form")
	}
	parts := strings.SplitN(repository, "/", 2)
	if parts[0] == "." || parts[0] == ".." || parts[1] == "." || parts[1] == ".." {
		return "", "", fmt.Errorf("GitHub repository must be in owner/name form")
	}
	return parts[0], parts[1], nil
}

func (c *GitHubClient) ListOpenIssues(ctx context.Context, repository string) ([]GitHubIssue, error) {
	owner, name, err := validateGitHubRepository(repository)
	if err != nil {
		return nil, err
	}
	endpoint := fmt.Sprintf("%s/repos/%s/%s/issues?state=open&per_page=%d&sort=updated&direction=desc",
		strings.TrimRight(c.baseURL, "/"), url.PathEscape(owner), url.PathEscape(name), maxGitHubIssues)
	var issues []GitHubIssue
	if err := c.getJSON(ctx, endpoint, &issues); err != nil {
		return nil, err
	}

	openIssues := make([]GitHubIssue, 0, len(issues))
	for _, issue := range issues {
		if len(issue.PullRequest) != 0 {
			continue
		}
		openIssues = append(openIssues, normalizeGitHubIssue(issue))
	}
	return openIssues, nil
}

func (c *GitHubClient) GetIssue(ctx context.Context, repository string, number int) (GitHubIssue, error) {
	owner, name, err := validateGitHubRepository(repository)
	if err != nil {
		return GitHubIssue{}, err
	}
	if number <= 0 {
		return GitHubIssue{}, fmt.Errorf("issue number must be positive")
	}
	endpoint := fmt.Sprintf("%s/repos/%s/%s/issues/%d",
		strings.TrimRight(c.baseURL, "/"), url.PathEscape(owner), url.PathEscape(name), number)
	var issue GitHubIssue
	if err := c.getJSON(ctx, endpoint, &issue); err != nil {
		return GitHubIssue{}, err
	}
	if len(issue.PullRequest) != 0 {
		return GitHubIssue{}, fmt.Errorf("#%d is a pull request, not an issue", number)
	}
	if issue.State != "open" {
		return GitHubIssue{}, fmt.Errorf("#%d is not an open issue", number)
	}
	if issue.Number == 0 {
		return GitHubIssue{}, fmt.Errorf("GitHub returned an invalid issue")
	}
	return normalizeGitHubIssue(issue), nil
}

func (c *GitHubClient) getJSON(ctx context.Context, endpoint string, target any) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return fmt.Errorf("create GitHub request: %w", err)
	}
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	request.Header.Set("User-Agent", "contribution-mentor")
	if c.token != "" {
		request.Header.Set("Authorization", "Bearer "+c.token)
	}

	response, err := c.http.Do(request)
	if err != nil {
		return fmt.Errorf("connect to GitHub API: %w", err)
	}
	defer response.Body.Close()

	body, err := io.ReadAll(io.LimitReader(response.Body, maxGitHubResponse+1))
	if err != nil {
		return fmt.Errorf("read GitHub response: %w", err)
	}
	if len(body) > maxGitHubResponse {
		return fmt.Errorf("GitHub response exceeded %d bytes", maxGitHubResponse)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		message := strings.TrimSpace(string(body))
		if response.StatusCode == http.StatusForbidden || response.StatusCode == http.StatusTooManyRequests {
			return fmt.Errorf("GitHub API returned %s (rate limit may be exceeded): %s", response.Status, message)
		}
		return fmt.Errorf("GitHub API returned %s: %s", response.Status, message)
	}
	if err := json.Unmarshal(body, target); err != nil {
		return fmt.Errorf("decode GitHub response: %w", err)
	}
	return nil
}

func normalizeGitHubIssue(issue GitHubIssue) GitHubIssue {
	issue.Body = truncateText(issue.Body, maxIssueBodySize)
	return issue
}

func truncateText(value string, maxBytes int) string {
	if len(value) <= maxBytes {
		return value
	}
	value = value[:maxBytes]
	for len(value) > 0 && !utf8.ValidString(value) {
		value = value[:len(value)-1]
	}
	return value + "\n[issue body truncated]"
}

func issueLabels(issue GitHubIssue) []string {
	labels := make([]string, 0, len(issue.Labels))
	for _, label := range issue.Labels {
		labels = append(labels, label.Name)
	}
	return labels
}

package mentor

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestModelClientAskUsesOpenAICompatibleEndpoint(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" {
			t.Errorf("unexpected request path %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer example-test-key" {
			t.Errorf("unexpected authorization header %q", r.Header.Get("Authorization"))
		}
		var request chatRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if request.Model != "provider/model-id" || request.Stream {
			t.Errorf("unexpected chat request settings: %+v", request)
		}
		if !strings.Contains(request.Messages[1].Content, "README.md") {
			t.Error("repository file was not included in prompt")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"Start with a focused improvement."}}]}`))
	}))
	defer server.Close()

	client, err := NewModelClient(ModelConfig{
		Provider: "custom-provider", BaseURL: server.URL + "/v1",
		Model: "provider/model-id", APIKey: "example-test-key",
	})
	if err != nil {
		t.Fatal(err)
	}
	answer, err := client.Ask(context.Background(), "What should I work on?", Repository{
		Root:  ".",
		Files: []RepositoryFile{{Path: "README.md", Content: "# Example"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if answer != "Start with a focused improvement." {
		t.Fatalf("unexpected answer: %q", answer)
	}
}

func TestNewModelClientValidatesConfiguration(t *testing.T) {
	for _, config := range []ModelConfig{
		{BaseURL: "https://example.com/v1", Model: "model"},
		{Provider: "provider", Model: "model"},
		{Provider: "provider", BaseURL: "https://example.com/v1"},
		{Provider: "provider", BaseURL: "localhost:11434/v1", Model: "model"},
		{Provider: "provider", BaseURL: "ftp://example.com/v1", Model: "model"},
		{Provider: "provider", BaseURL: "https://user:pass@example.com/v1", Model: "model"},
		{Provider: "provider", BaseURL: "https://example.com/v1?key=secret", Model: "model"},
	} {
		if _, err := NewModelClient(config); err == nil {
			t.Errorf("expected config %+v to be rejected", config)
		}
	}
	if _, err := NewModelClient(ModelConfig{
		Provider: "any-provider", BaseURL: "https://api.example.com/v1", Model: "any-model-id",
	}); err != nil {
		t.Fatalf("expected provider and model names to be configurable: %v", err)
	}
}

func TestGitHubListOpenIssuesExcludesPullRequests(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/repos/example/project/issues" {
			t.Errorf("unexpected API path %s", r.URL.Path)
		}
		if r.URL.Query().Get("state") != "open" || r.URL.Query().Get("per_page") != "20" {
			t.Errorf("unexpected issue query: %s", r.URL.RawQuery)
		}
		if r.Header.Get("User-Agent") == "" {
			t.Error("missing GitHub API User-Agent")
		}
		if r.Header.Get("Authorization") != "Bearer example-gh-test-key" {
			t.Error("optional GitHub token was not added to the request")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[
			{"number":1,"title":"Fix parser","body":"Add a test","html_url":"https://github.com/example/project/issues/1","state":"open","labels":[{"name":"good first issue"}]},
			{"number":2,"title":"Pull request","html_url":"https://github.com/example/project/pull/2","state":"open","pull_request":{"url":"https://api.github.com/repos/example/project/pulls/2"}}
		]`))
	}))
	defer server.Close()

	client := NewGitHubClient()
	client.baseURL = server.URL
	client.token = "example-gh-test-key"
	issues, err := client.ListOpenIssues(context.Background(), "example/project")
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 1 || issues[0].Number != 1 {
		t.Fatalf("expected only issue #1, got %+v", issues)
	}
	if got := issueLabels(issues[0]); len(got) != 1 || got[0] != "good first issue" {
		t.Fatalf("unexpected issue labels: %v", got)
	}
}

func TestGitHubRejectsInvalidRepositoryAndClosedIssue(t *testing.T) {
	client := NewGitHubClient()
	if _, err := client.ListOpenIssues(context.Background(), "https://github.com/example/project"); err == nil {
		t.Fatal("expected full URL to be rejected")
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"number":7,"title":"Closed issue","state":"closed"}`))
	}))
	defer server.Close()
	client.baseURL = server.URL
	if _, err := client.GetIssue(context.Background(), "example/project", 7); err == nil {
		t.Fatal("expected closed issue to be rejected")
	}
}

func TestModelClientIssueRecommendationIncludesExperienceAndIssues(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request chatRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		content := request.Messages[1].Content
		for _, expected := range []string{"beginner Go developer", "Fix parser", "https://github.com/example/project/issues/1"} {
			if !strings.Contains(content, expected) {
				t.Errorf("prompt is missing %q", expected)
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"Issue #1 is the best match."}}]}`))
	}))
	defer server.Close()

	client, err := NewModelClient(ModelConfig{
		Provider: "openai-compatible", BaseURL: server.URL + "/v1", Model: "any-model",
	})
	if err != nil {
		t.Fatal(err)
	}
	answer, err := client.RecommendIssues(context.Background(), "beginner Go developer", []GitHubIssue{{
		Number: 1, Title: "Fix parser", HTMLURL: "https://github.com/example/project/issues/1",
		State: "open",
	}}, Repository{Root: ".", Files: []RepositoryFile{{Path: "README.md", Content: "# Example"}}})
	if err != nil {
		t.Fatal(err)
	}
	if answer != "Issue #1 is the best match." {
		t.Fatalf("unexpected answer: %q", answer)
	}
}

func TestApplyApprovedIssueChangesRequiresConfirmation(t *testing.T) {
	root := t.TempDir()
	readme := filepath.Join(root, "README.md")
	if err := os.WriteFile(readme, []byte("# Original\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	repo := Repository{
		Root:  root,
		Files: []RepositoryFile{{Path: "README.md", Content: "# Original\n"}},
	}
	change := []IssueChange{
		{Path: "README.md", Action: "modify", Content: "# Updated\n"},
		{Path: "docs/guide.md", Action: "create", Content: "# Guide\n"},
	}

	applied, err := ApplyApprovedIssueChanges(repo, change, strings.NewReader("no\n"), &bytes.Buffer{})
	if err != nil {
		t.Fatal(err)
	}
	if applied {
		t.Fatal("changes were applied without explicit approval")
	}
	content, err := os.ReadFile(readme)
	if err != nil {
		t.Fatal(err)
	}
	if string(content) != "# Original\n" {
		t.Fatalf("readme changed after cancellation: %q", content)
	}
	if _, err := os.Stat(filepath.Join(root, "docs", "guide.md")); !os.IsNotExist(err) {
		t.Fatal("new file was created after cancellation")
	}

	applied, err = ApplyApprovedIssueChanges(repo, change, strings.NewReader("APPLY\n"), &bytes.Buffer{})
	if err != nil {
		t.Fatal(err)
	}
	if !applied {
		t.Fatal("expected explicit approval to apply changes")
	}
	content, err = os.ReadFile(readme)
	if err != nil {
		t.Fatal(err)
	}
	if string(content) != "# Updated\n" {
		t.Fatalf("unexpected updated readme: %q", content)
	}
}

func TestPrepareIssueChangesRejectsUnsafePathsAndStaleContent(t *testing.T) {
	root := t.TempDir()
	readme := filepath.Join(root, "README.md")
	if err := os.WriteFile(readme, []byte("# Changed elsewhere\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	repo := Repository{
		Root:  root,
		Files: []RepositoryFile{{Path: "README.md", Content: "# Original\n"}},
	}
	for _, change := range []IssueChange{
		{Path: "../outside.md", Action: "create", Content: "# Bad"},
		{Path: ".env", Action: "create", Content: "API_KEY=secret"},
		{Path: "README.md", Action: "modify", Content: "# Proposed"},
	} {
		if _, err := prepareIssueChanges(repo, []IssueChange{change}); err == nil {
			t.Errorf("expected proposed change %q to be rejected", change.Path)
		}
	}
}

func TestApplyApprovedIssueChangesRejectsSymlinkPaths(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if err := os.Symlink(outside, filepath.Join(root, "linked")); err != nil {
		t.Skipf("symlink not available: %v", err)
	}
	repo := Repository{Root: root}
	if _, err := prepareIssueChanges(repo, []IssueChange{{
		Path: "linked/new.md", Action: "create", Content: "# Not allowed\n",
	}}); err == nil {
		t.Fatal("expected symlink path to be rejected")
	}
}

func TestGenerateIssueChangesParsesModelProposal(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request chatRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(request.Messages[1].Content, "Selected open GitHub issue") {
			t.Error("selected issue missing from change-generation prompt")
		}
		if !strings.Contains(request.Messages[0].Content, "untrusted data") {
			t.Error("model system prompt does not mark repository content as untrusted")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"{\"changes\":[{\"path\":\"README.md\",\"action\":\"modify\",\"content\":\"# Updated\\n\"}]}"}}]}`))
	}))
	defer server.Close()

	client, err := NewModelClient(ModelConfig{
		Provider: "openai-compatible", BaseURL: server.URL + "/v1", Model: "any-model",
	})
	if err != nil {
		t.Fatal(err)
	}
	changes, err := client.GenerateIssueChanges(context.Background(), "beginner Go developer", GitHubIssue{
		Number: 1, Title: "Update docs", State: "open",
	}, Repository{Root: ".", Files: []RepositoryFile{{Path: "README.md", Content: "# Original"}}})
	if err != nil {
		t.Fatal(err)
	}
	if len(changes) != 1 || changes[0].Path != "README.md" || changes[0].Action != "modify" || changes[0].Content != "# Updated\n" {
		t.Fatalf("unexpected changes: %+v", changes)
	}
}

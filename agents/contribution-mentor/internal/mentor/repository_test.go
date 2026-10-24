package mentor

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestInspectRepositorySkipsSensitiveFiles(t *testing.T) {
	root := t.TempDir()
	files := map[string]string{
		"README.md":            "# Demo\n",
		".env":                 "API_KEY=do-not-send\n",
		".env.local":           "PRIVATE=value\n",
		"credentials.json":     `{"token":"do-not-send"}`,
		".env.example":         "API_KEY=placeholder\n",
		"src/main.go":          "package main\n",
		"node_modules/deps.js": "ignored\n",
	}
	for name, content := range files {
		filePath := filepath.Join(root, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(filePath), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filePath, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	repo, err := InspectRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	included := map[string]bool{}
	for _, file := range repo.Files {
		included[file.Path] = true
		if strings.Contains(file.Content, "do-not-send") {
			t.Errorf("sensitive content was included from %s", file.Path)
		}
	}
	for _, name := range []string{"README.md", ".env.example", "src/main.go"} {
		if !included[name] {
			t.Errorf("expected %s to be included", name)
		}
	}
	for _, name := range []string{".env", ".env.local", "credentials.json", "node_modules/deps.js"} {
		if included[name] {
			t.Errorf("did not expect %s to be included", name)
		}
	}
}

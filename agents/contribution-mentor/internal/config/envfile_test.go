package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadDotEnv(t *testing.T) {
	filename := filepath.Join(t.TempDir(), ".env")
	if err := os.WriteFile(filename, []byte("# comment\nDOTENV_TEST_VALUE=\"from file\"\nexport DOTENV_TEST_OTHER='single quoted'\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("DOTENV_TEST_VALUE", "from process")
	t.Setenv("DOTENV_TEST_OTHER", "")
	if err := LoadDotEnv(filename); err != nil {
		t.Fatal(err)
	}
	if got := os.Getenv("DOTENV_TEST_VALUE"); got != "from process" {
		t.Errorf("process environment should take precedence, got %q", got)
	}
	if got := os.Getenv("DOTENV_TEST_OTHER"); got != "" {
		t.Errorf("existing empty process environment should be preserved, got %q", got)
	}
	if err := os.Unsetenv("DOTENV_TEST_OTHER"); err != nil {
		t.Fatal(err)
	}
	if err := LoadDotEnv(filename); err != nil {
		t.Fatal(err)
	}
	if got := os.Getenv("DOTENV_TEST_OTHER"); got != "single quoted" {
		t.Errorf("quoted value was not loaded, got %q", got)
	}
}

func TestLoadDotEnvRejectsMalformedLines(t *testing.T) {
	filename := filepath.Join(t.TempDir(), ".env")
	if err := os.WriteFile(filename, []byte("not-a-key-value\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := LoadDotEnv(filename); err == nil {
		t.Fatal("expected malformed environment file to be rejected")
	}
}

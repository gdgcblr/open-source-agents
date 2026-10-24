package main

import (
	"bufio"
	"log"
	"os"
	"path/filepath"
	"strings"
)

func loadDotEnvFromWorkingTree() {
	wd, err := os.Getwd()
	if err != nil {
		return
	}
	dir := wd
	for i := 0; i < 6; i++ {
		path := filepath.Join(dir, ".env")
		if _, err := os.Stat(path); err == nil {
			loadDotEnvFile(path)
			return
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	log.Printf("no .env found (cwd: %s)", wd)
}

// loadDotEnvFile sets variables from path, overriding empty or placeholder env values.
func loadDotEnvFile(path string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "export ") {
			line = strings.TrimSpace(strings.TrimPrefix(line, "export "))
		}
		key, val, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		val = strings.TrimSpace(val)
		val = strings.Trim(val, `"'`)
		if key == "" {
			continue
		}
		current := os.Getenv(key)
		if !shouldOverrideEnv(key, current) {
			continue
		}
		_ = os.Setenv(key, val)
	}
	log.Printf("loaded environment from %s", path)
}

func shouldOverrideEnv(key, current string) bool {
	if current == "" {
		return true
	}
	if key == "OPENAI_API_KEY" && (strings.Contains(current, "your_openai") || strings.Contains(current, "REPLACE")) {
		return true
	}
	if key == "GOOGLE_API_KEY" || key == "GEMINI_API_KEY" {
		if strings.Contains(current, "your_") || strings.Contains(current, "REPLACE") {
			return true
		}
	}
	return false
}

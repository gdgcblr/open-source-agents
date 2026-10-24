package mentor

import (
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf8"
)

const (
	maxFiles          = 80
	maxFileBytes      = 12 * 1024
	maxTotalTextBytes = 72 * 1024
)

type Repository struct {
	Root    string
	Files   []RepositoryFile
	Skipped int
}

type RepositoryFile struct {
	Path    string
	Content string
}

var ignoredDirectories = map[string]bool{
	".git": true, ".idea": true, ".venv": true, "build": true,
	"dist": true, "node_modules": true, "target": true, "vendor": true, "venv": true,
}

var includedExtensions = map[string]bool{
	".c": true, ".cc": true, ".cfg": true, ".cpp": true, ".cs": true,
	".css": true, ".go": true, ".html": true, ".java": true, ".js": true,
	".json": true, ".jsx": true, ".md": true, ".mod": true, ".py": true,
	".rst": true, ".rs": true, ".scss": true, ".sh": true, ".sum": true,
	".toml": true, ".ts": true, ".tsx": true, ".txt": true, ".xml": true,
	".yaml": true, ".yml": true,
}

func InspectRepository(path string) (Repository, error) {
	root, err := filepath.Abs(path)
	if err != nil {
		return Repository{}, fmt.Errorf("resolve path: %w", err)
	}
	info, err := os.Stat(root)
	if err != nil {
		return Repository{}, fmt.Errorf("read path: %w", err)
	}
	if !info.IsDir() {
		return Repository{}, fmt.Errorf("%q is not a directory", root)
	}

	repo := Repository{Root: root}
	totalBytes := 0
	err = filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == root {
			return nil
		}

		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if ignoredDirectories[strings.ToLower(entry.Name())] {
				return filepath.SkipDir
			}
			return nil
		}
		if !entry.Type().IsRegular() || !isRelevantFile(entry.Name()) {
			repo.Skipped++
			return nil
		}
		if len(repo.Files) >= maxFiles || totalBytes >= maxTotalTextBytes {
			repo.Skipped++
			return nil
		}

		file, err := os.Open(path)
		if err != nil {
			return fmt.Errorf("open %s: %w", relative, err)
		}
		content, readErr := io.ReadAll(io.LimitReader(file, maxFileBytes+1))
		closeErr := file.Close()
		if readErr != nil {
			return fmt.Errorf("read %s: %w", relative, readErr)
		}
		if closeErr != nil {
			return fmt.Errorf("close %s: %w", relative, closeErr)
		}
		if len(content) > maxFileBytes || bytesContainNUL(content) || !utf8.Valid(content) {
			repo.Skipped++
			return nil
		}

		remaining := maxTotalTextBytes - totalBytes
		if len(content) > remaining {
			content = content[:remaining]
			repo.Skipped++
		}
		repo.Files = append(repo.Files, RepositoryFile{
			Path:    filepath.ToSlash(relative),
			Content: string(content),
		})
		totalBytes += len(content)
		return nil
	})
	if err != nil {
		return Repository{}, fmt.Errorf("walk repository: %w", err)
	}
	sort.Slice(repo.Files, func(i, j int) bool {
		return repo.Files[i].Path < repo.Files[j].Path
	})
	if len(repo.Files) == 0 {
		return Repository{}, fmt.Errorf("no supported text files found in %q", root)
	}
	return repo, nil
}

func isRelevantFile(name string) bool {
	lower := strings.ToLower(name)
	if isSensitiveFilename(lower) {
		return false
	}
	if lower == ".env.example" || lower == "dockerfile" || lower == "makefile" || lower == ".gitignore" {
		return true
	}
	return includedExtensions[filepath.Ext(lower)]
}

func isSensitiveFilename(name string) bool {
	if name == ".env" {
		return true
	}
	if strings.HasPrefix(name, ".env.") && name != ".env.example" {
		return true
	}
	for _, fragment := range []string{"credential", "secret", "private-key", "service-account"} {
		if strings.Contains(name, fragment) {
			return true
		}
	}
	for _, extension := range []string{".pem", ".key", ".p12", ".pfx", ".crt", ".cert"} {
		if strings.HasSuffix(name, extension) {
			return true
		}
	}
	return false
}

func bytesContainNUL(content []byte) bool {
	for _, b := range content {
		if b == 0 {
			return true
		}
	}
	return false
}

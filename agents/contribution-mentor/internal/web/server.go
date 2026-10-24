package web

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"contribution-mentor/internal/mentor"
)

const (
	webRequestLimit  = 16 * 1024
	checkOutputLimit = 1024 * 1024
)

//go:embed static/*
var webFiles embed.FS

type webServer struct {
	model *mentor.ModelClient
}

type askRequest struct {
	Repository string `json:"repository"`
	Question   string `json:"question"`
}

type checkRequest struct {
	Repository string `json:"repository"`
	Check      string `json:"check"`
}

type askResponse struct {
	Answer string `json:"answer"`
}

type checkResponse struct {
	Command   string `json:"command"`
	Output    string `json:"output"`
	ExitCode  int    `json:"exitCode"`
	Truncated bool   `json:"truncated"`
}

type cappedBuffer struct {
	mu        sync.Mutex
	data      []byte
	limit     int
	truncated bool
}

func (b *cappedBuffer) Write(data []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	remaining := b.limit - len(b.data)
	if remaining <= 0 {
		b.truncated = true
		return len(data), nil
	}
	if len(data) > remaining {
		b.data = append(b.data, data[:remaining]...)
		b.truncated = true
		return len(data), nil
	}
	b.data = append(b.data, data...)
	return len(data), nil
}

func (b *cappedBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return string(b.data)
}

func Start(address string, client *mentor.ModelClient) error {
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return fmt.Errorf("listen on %s: %w", address, err)
	}
	server := &http.Server{
		Handler:           NewHandler(client),
		ReadHeaderTimeout: 5 * time.Second,
	}
	if err := server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return fmt.Errorf("serve HTTP: %w", err)
	}
	return nil
}

func NewHandler(client *mentor.ModelClient) http.Handler {
	mux := http.NewServeMux()
	server := &webServer{model: client}
	mux.HandleFunc("/", server.serveIndex)
	mux.HandleFunc("/api/ask", server.ask)
	mux.HandleFunc("/api/check", server.check)
	return localOnlyHandler(mux)
}

func localOnlyHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.Host)
		if err != nil || !isLoopbackHost(host) {
			http.Error(w, "web interface is available only on localhost", http.StatusForbidden)
			return
		}
		if r.Method == http.MethodPost && r.Header.Get("Origin") != "http://"+r.Host {
			http.Error(w, "cross-origin requests are not allowed", http.StatusForbidden)
			return
		}
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
		next.ServeHTTP(w, r)
	})
}

func isLoopbackHost(host string) bool {
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback() || strings.EqualFold(host, "localhost")
}

func (s *webServer) serveIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", http.MethodGet)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	page, err := webFiles.ReadFile("static/index.html")
	if err != nil {
		http.Error(w, "web interface is unavailable", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write(page)
}

func (s *webServer) ask(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var input askRequest
	if err := decodeWebRequest(w, r, &input); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(input.Question) == "" {
		http.Error(w, "question is required", http.StatusBadRequest)
		return
	}
	repository, err := mentor.InspectRepository(input.Repository)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	answer, err := s.model.Ask(ctx, input.Question, repository)
	if err != nil {
		http.Error(w, fmt.Sprintf("ask model provider: %v", err), http.StatusBadGateway)
		return
	}
	writeJSON(w, askResponse{Answer: answer})
}

func (s *webServer) check(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var input checkRequest
	if err := decodeWebRequest(w, r, &input); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	repository, err := resolveGoRepository(input.Repository)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	args, command, ok := goCheckCommand(input.Check)
	if !ok {
		http.Error(w, "check must be test or vet", http.StatusBadRequest)
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 10*time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, "go", args...)
	cmd.Dir = repository
	output := &cappedBuffer{limit: checkOutputLimit}
	cmd.Stdout = output
	cmd.Stderr = output
	runErr := cmd.Run()

	result := checkResponse{
		Command: command, Output: output.String(), ExitCode: 0, Truncated: output.truncated,
	}
	if runErr != nil {
		result.ExitCode = 1
		var exitError *exec.ExitError
		if errors.As(runErr, &exitError) {
			result.ExitCode = exitError.ExitCode()
		} else if ctx.Err() != nil {
			result.Output += "\n" + ctx.Err().Error()
			result.ExitCode = -1
		} else {
			http.Error(w, fmt.Sprintf("run %s: %v", command, runErr), http.StatusInternalServerError)
			return
		}
	}
	writeJSON(w, result)
}

func decodeWebRequest(w http.ResponseWriter, r *http.Request, destination any) error {
	if r.Header.Get("Content-Type") != "application/json" {
		return fmt.Errorf("content type must be application/json")
	}
	r.Body = http.MaxBytesReader(w, r.Body, webRequestLimit)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return fmt.Errorf("invalid request: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return fmt.Errorf("request must contain one JSON object")
		}
		return fmt.Errorf("invalid request: %w", err)
	}
	return nil
}

func resolveGoRepository(path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", fmt.Errorf("repository path is required")
	}
	root, err := filepath.Abs(path)
	if err != nil {
		return "", fmt.Errorf("resolve repository path: %w", err)
	}
	info, err := os.Stat(root)
	if err != nil {
		return "", fmt.Errorf("read repository path: %w", err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("repository path must be a directory")
	}
	module, err := os.Stat(filepath.Join(root, "go.mod"))
	if err != nil {
		return "", fmt.Errorf("Go checks require a go.mod file at the repository root: %w", err)
	}
	if !module.Mode().IsRegular() {
		return "", fmt.Errorf("go.mod must be a regular file at the repository root")
	}
	return root, nil
}

func goCheckCommand(check string) ([]string, string, bool) {
	switch check {
	case "test":
		return []string{"test", "./..."}, "go test ./...", true
	case "vet":
		return []string{"vet", "./..."}, "go vet ./...", true
	default:
		return nil, "", false
	}
}

func writeJSON(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if err := json.NewEncoder(w).Encode(value); err != nil {
		http.Error(w, "encode response", http.StatusInternalServerError)
	}
}

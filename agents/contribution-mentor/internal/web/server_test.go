package web

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"contribution-mentor/internal/mentor"
)

func TestWebServesInterfaceOnlyOnLoopback(t *testing.T) {
	handler := NewHandler(nil)
	request := httptest.NewRequest(http.MethodGet, "/", nil)
	request.Host = "127.0.0.1:8080"
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", response.Code)
	}
	if !strings.Contains(response.Body.String(), "Run go test ./...") {
		t.Error("web interface is missing the Go test action")
	}

	remoteRequest := httptest.NewRequest(http.MethodGet, "/", nil)
	remoteRequest.Host = "192.0.2.5:8080"
	remoteResponse := httptest.NewRecorder()
	handler.ServeHTTP(remoteResponse, remoteRequest)
	if remoteResponse.Code != http.StatusForbidden {
		t.Fatalf("expected remote host to be rejected, got %d", remoteResponse.Code)
	}
}

func TestWebAskUsesConfiguredModel(t *testing.T) {
	modelServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Messages []struct {
				Content string `json:"content"`
			} `json:"messages"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		if len(request.Messages) < 2 || !strings.Contains(request.Messages[1].Content, "README.md") {
			t.Error("expected repository context in model request")
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"Run the focused tests first."}}]}`))
	}))
	defer modelServer.Close()
	client, err := mentor.NewModelClient(mentor.ModelConfig{
		Provider: "test", BaseURL: modelServer.URL + "/v1", Model: "test-model",
	})
	if err != nil {
		t.Fatal(err)
	}

	repository := t.TempDir()
	if err := os.WriteFile(filepath.Join(repository, "README.md"), []byte("# Example\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	body := `{"repository":` + jsonString(repository) + `,"question":"How do I test this?"}`
	request := httptest.NewRequest(http.MethodPost, "/api/ask", strings.NewReader(body))
	setLocalWebHeaders(request)
	response := httptest.NewRecorder()

	NewHandler(client).ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", response.Code, response.Body.String())
	}
	var result askResponse
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	if result.Answer != "Run the focused tests first." {
		t.Fatalf("unexpected answer: %q", result.Answer)
	}
}

func TestWebCheckRunsFixedGoTestCommand(t *testing.T) {
	repository := t.TempDir()
	if err := os.WriteFile(filepath.Join(repository, "go.mod"), []byte("module example.com/webcheck\n\ngo 1.22\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(repository, "sample_test.go"), []byte("package webcheck\n\nimport \"testing\"\n\nfunc TestPass(t *testing.T) {}\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	body := `{"repository":` + jsonString(repository) + `,"check":"test"}`
	request := httptest.NewRequest(http.MethodPost, "/api/check", strings.NewReader(body))
	setLocalWebHeaders(request)
	response := httptest.NewRecorder()

	NewHandler(nil).ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", response.Code, response.Body.String())
	}
	var result checkResponse
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	if result.Command != "go test ./..." || result.ExitCode != 0 {
		t.Fatalf("unexpected check result: %+v", result)
	}
}

func TestWebRejectsCrossOriginAndUnknownChecks(t *testing.T) {
	repository := t.TempDir()
	if err := os.WriteFile(filepath.Join(repository, "go.mod"), []byte("module example.com/webcheck\n\ngo 1.22\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	handler := NewHandler(nil)

	crossOrigin := httptest.NewRequest(http.MethodPost, "/api/check", strings.NewReader(`{"repository":"`+repository+`","check":"test"}`))
	crossOrigin.Host = "127.0.0.1:8080"
	crossOrigin.Header.Set("Origin", "http://evil.example")
	crossOrigin.Header.Set("Content-Type", "application/json")
	crossOriginResponse := httptest.NewRecorder()
	handler.ServeHTTP(crossOriginResponse, crossOrigin)
	if crossOriginResponse.Code != http.StatusForbidden {
		t.Fatalf("expected cross-origin request to be rejected, got %d", crossOriginResponse.Code)
	}

	unknownCheck := httptest.NewRequest(http.MethodPost, "/api/check", strings.NewReader(`{"repository":`+jsonString(repository)+`,"check":"clean"}`))
	setLocalWebHeaders(unknownCheck)
	unknownCheckResponse := httptest.NewRecorder()
	handler.ServeHTTP(unknownCheckResponse, unknownCheck)
	if unknownCheckResponse.Code != http.StatusBadRequest {
		t.Fatalf("expected unknown check to be rejected, got %d", unknownCheckResponse.Code)
	}
}

func TestResolveGoRepositoryRequiresModuleRoot(t *testing.T) {
	repository := t.TempDir()
	if _, err := resolveGoRepository(repository); err == nil {
		t.Fatal("expected repository without go.mod to be rejected")
	}
	if _, _, ok := goCheckCommand("arbitrary"); ok {
		t.Fatal("expected unsupported command to be rejected")
	}
}

func setLocalWebHeaders(request *http.Request) {
	request.Host = "127.0.0.1:8080"
	request.Header.Set("Origin", "http://127.0.0.1:8080")
	request.Header.Set("Content-Type", "application/json")
}

func jsonString(value string) string {
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

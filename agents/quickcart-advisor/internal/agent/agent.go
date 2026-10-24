package agent

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"
	"time"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/agent/llmagent"
	"google.golang.org/adk/v2/model"
	"google.golang.org/adk/v2/model/gemini"
	"google.golang.org/adk/v2/model/openaimodel"
	"google.golang.org/adk/v2/runner"
	"google.golang.org/adk/v2/session"
	"google.golang.org/genai"

	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/tools"
)

// appName is the ADK application name sessions are scoped to.
const appName = "quickcart-advisor"

const (
	// BackendOpenAI selects an OpenAI-compatible Chat Completions endpoint,
	// e.g. a local LM Studio server. Backend "openai-compatible" is accepted
	// as an alias.
	BackendOpenAI = "openai"
	// BackendGemini selects Google Gemini via the genai client.
	BackendGemini = "gemini"
)

// Config carries everything New needs to build the agent.
type Config struct {
	// Backend is "openai" (OpenAI-compatible Chat Completions, e.g. LM
	// Studio) or "gemini".
	Backend string
	// ModelName is the backend-specific model identifier.
	ModelName string
	// BaseURL is the endpoint for the openai backend; ignored for gemini.
	BaseURL string
	// APIKey authenticates against the backend. LM Studio accepts any
	// non-empty placeholder.
	APIKey string
	// QBuysBaseURL is the base URL of the qbuys live-data service. It is
	// carried for wiring symmetry with tools.NewDeps; the data-source stack
	// itself lives in the injected tools.Deps.
	QBuysBaseURL string
}

// App is a constructed QuickCart Advisor: the runner, its session service,
// and the deps, ready to serve RunOnce calls.
type App struct {
	runner   *runner.Runner
	sessions session.Service
	deps     *tools.Deps
	// AppName is the ADK application name sessions are created under.
	AppName string
}

// New builds the model for cfg.Backend, assembles the five function tools
// from deps, constructs the single LLM agent with Instruction() as its system
// prompt, and wraps it in a runner over an in-memory session service.
func New(ctx context.Context, cfg Config, deps *tools.Deps) (*App, error) {
	if deps == nil {
		return nil, fmt.Errorf("agent.New: deps must not be nil")
	}

	llm, err := newModel(ctx, cfg)
	if err != nil {
		return nil, err
	}

	toolSet, err := deps.All()
	if err != nil {
		return nil, fmt.Errorf("agent.New: build tools: %w", err)
	}

	ag, err := llmagent.New(llmagent.Config{
		Name:        "quickcart_advisor",
		Description: "Compares a product across Swiggy Instamart, Blinkit, Zepto, and Amazon India and recommends where to buy by total delivered cost, fees, ETA, and memberships.",
		Model:       llm,
		Instruction: Instruction(),
		Tools:       toolSet,
		// Single-agent app: there is no parent or peer to transfer to.
		DisallowTransferToParent: true,
		DisallowTransferToPeers:  true,
	})
	if err != nil {
		return nil, fmt.Errorf("agent.New: build llm agent: %w", err)
	}

	sessions := session.InMemoryService()
	r, err := runner.New(runner.Config{
		AppName:        appName,
		Agent:          ag,
		SessionService: sessions,
	})
	if err != nil {
		return nil, fmt.Errorf("agent.New: build runner: %w", err)
	}

	return &App{
		runner:   r,
		sessions: sessions,
		deps:     deps,
		AppName:  appName,
	}, nil
}

// newModel constructs the LLM backend selected by cfg.
func newModel(ctx context.Context, cfg Config) (model.LLM, error) {
	if cfg.ModelName == "" {
		return nil, fmt.Errorf("agent.New: ModelName must not be empty")
	}

	switch strings.ToLower(strings.TrimSpace(cfg.Backend)) {
	case BackendOpenAI, "openai-compatible":
		return openaimodel.NewModel(ctx, cfg.ModelName, &openaimodel.ClientConfig{
			APIKey:  cfg.APIKey,
			BaseURL: cfg.BaseURL,
			// LM Studio and similar servers implement Chat Completions,
			// not the Responses API.
			API: openaimodel.APIChatCompletions,
		})
	case BackendGemini:
		return gemini.NewModel(ctx, cfg.ModelName, &genai.ClientConfig{
			APIKey: cfg.APIKey,
		})
	default:
		return nil, fmt.Errorf("agent.New: unsupported backend %q (want %q or %q)", cfg.Backend, BackendOpenAI, BackendGemini)
	}
}

// RunOnce runs a single self-contained conversation: it creates a fresh
// in-memory session, sends userMsg, drives the agent (including its tool
// calls) to completion, and returns the concatenated final-response text.
// Non-final streaming events and chain-of-thought parts are excluded.
func (a *App) RunOnce(ctx context.Context, userMsg string) (string, error) {
	if a == nil || a.runner == nil || a.sessions == nil {
		return "", fmt.Errorf("agent.RunOnce: App is not initialized")
	}
	userMsg = strings.TrimSpace(userMsg)
	if userMsg == "" {
		return "", fmt.Errorf("agent.RunOnce: user message must not be empty")
	}

	userID := "user-" + newID()
	sessionID := newID()
	if _, err := a.sessions.Create(ctx, &session.CreateRequest{
		AppName:   a.AppName,
		UserID:    userID,
		SessionID: sessionID,
	}); err != nil {
		return "", fmt.Errorf("agent.RunOnce: create session: %w", err)
	}

	msg := &genai.Content{
		Role:  "user",
		Parts: []*genai.Part{{Text: userMsg}},
	}

	var sb strings.Builder
	for ev, err := range a.runner.Run(ctx, userID, sessionID, msg, agent.RunConfig{}) {
		if err != nil {
			return sb.String(), fmt.Errorf("agent.RunOnce: run agent: %w", err)
		}
		if ev == nil || !ev.IsFinalResponse() || ev.Content == nil {
			continue
		}
		for _, p := range ev.Content.Parts {
			if p == nil || p.Thought {
				continue
			}
			sb.WriteString(p.Text)
		}
	}
	return sb.String(), nil
}

// newID returns a random 128-bit hex identifier for sessions and users. It
// falls back to a time-and-counter value if the system entropy source fails,
// keeping RunOnce panic-free even in degraded environments.
func newID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		fallbackMu.Lock()
		fallbackCounter++
		c := fallbackCounter
		fallbackMu.Unlock()
		return fmt.Sprintf("fallback-%d-%d", time.Now().UnixNano(), c)
	}
	return hex.EncodeToString(b[:])
}

var (
	fallbackMu      sync.Mutex
	fallbackCounter uint64
)

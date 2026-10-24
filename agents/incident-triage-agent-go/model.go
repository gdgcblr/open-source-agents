package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"time"

	"google.golang.org/genai"

	"google.golang.org/adk/v2/model"
	"google.golang.org/adk/v2/model/gemini"
	"google.golang.org/adk/v2/model/openaimodel"
)

// modelCallTimeout bounds every model call, so one slow call cannot consume
// the whole investigation.
const modelCallTimeout = 90 * time.Second

// newModel picks the LLM backend from MODEL_PROVIDER:
//   - "gemini" (default): Gemini API, needs GOOGLE_API_KEY.
//   - "openai": any OpenAI-compatible Chat Completions server, e.g. a local
//     open-weights model in Ollama, vLLM or llama.cpp (OPENAI_BASE_URL).
//     With a local server, metrics and logs never leave the machine.
func newModel(ctx context.Context) (model.LLM, string, error) {
	switch provider := env("MODEL_PROVIDER", "gemini"); provider {
	case "gemini":
		name := env("MODEL_NAME", "gemini-flash-latest")
		key := os.Getenv("GOOGLE_API_KEY")
		if key == "" {
			return nil, "", fmt.Errorf("GOOGLE_API_KEY is not set (copy .env.example to .env and add your key)")
		}
		timeout := modelCallTimeout
		m, err := gemini.NewModel(ctx, name, &genai.ClientConfig{
			APIKey: key,
			HTTPOptions: genai.HTTPOptions{
				Timeout: &timeout,
				RetryOptions: &genai.HTTPRetryOptions{
					Attempts:        genai.Ptr[int32](3),
					HTTPStatusCodes: []int32{429, 500, 502, 503, 504},
				},
			},
		})
		return m, "gemini/" + name, err
	case "openai":
		name := env("MODEL_NAME", "qwen3:8b")
		m, err := openaimodel.NewModel(ctx, name, &openaimodel.ClientConfig{
			APIKey:     env("OPENAI_API_KEY", "local"),
			BaseURL:    env("OPENAI_BASE_URL", "http://localhost:11434/v1"),
			API:        openaimodel.APIChatCompletions,
			HTTPClient: &http.Client{Timeout: modelCallTimeout},
		})
		return m, "openai/" + name, err
	default:
		return nil, "", fmt.Errorf("unknown MODEL_PROVIDER %q (use gemini or openai)", provider)
	}
}

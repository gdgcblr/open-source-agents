package main

import (
	"context"
	"fmt"
	"os"
	"strings"

	"google.golang.org/adk/v2/model"
	"google.golang.org/adk/v2/model/gemini"
	"google.golang.org/adk/v2/model/openaimodel"
	"google.golang.org/genai"
)

// newLLM selects Gemini or OpenAI from LLM_PROVIDER and environment variables.
func newLLM(ctx context.Context) (model.LLM, string, error) {
	provider := strings.ToLower(strings.TrimSpace(os.Getenv("LLM_PROVIDER")))
	if provider == "" {
		switch {
		case os.Getenv("OPENAI_API_KEY") != "":
			provider = "openai"
		case os.Getenv("GOOGLE_API_KEY") != "" || os.Getenv("GEMINI_API_KEY") != "":
			provider = "gemini"
		default:
			return nil, "", fmt.Errorf("set OPENAI_API_KEY (LLM_PROVIDER=openai) or GOOGLE_API_KEY / GEMINI_API_KEY (LLM_PROVIDER=gemini)")
		}
	}

	modelName := strings.TrimSpace(os.Getenv("MODEL_NAME"))

	switch provider {
	case "openai":
		apiKey := strings.TrimSpace(os.Getenv("OPENAI_API_KEY"))
		if apiKey == "" || strings.Contains(apiKey, "your_openai") {
			return nil, "", fmt.Errorf("LLM_PROVIDER=openai requires a valid OPENAI_API_KEY in the environment or .env file")
		}
		if !strings.HasPrefix(apiKey, "sk-proj-") && !strings.HasPrefix(apiKey, "sk-") {
			return nil, "", fmt.Errorf("OPENAI_API_KEY does not look like an OpenAI secret key (expected sk- or sk-proj- prefix)")
		}
		if modelName == "" {
			modelName = "gpt-4o-mini"
		}
		llm, err := openaimodel.NewModel(ctx, modelName, &openaimodel.ClientConfig{
			APIKey: apiKey,
			API:    openaimodel.APIChatCompletions,
		})
		return llm, modelName, err

	case "gemini":
		apiKey := os.Getenv("GOOGLE_API_KEY")
		if apiKey == "" {
			apiKey = os.Getenv("GEMINI_API_KEY")
		}
		if apiKey == "" {
			return nil, "", fmt.Errorf("LLM_PROVIDER=gemini requires GOOGLE_API_KEY or GEMINI_API_KEY")
		}
		if modelName == "" {
			modelName = "gemini-2.5-flash"
		}
		llm, err := gemini.NewModel(ctx, modelName, &genai.ClientConfig{APIKey: apiKey})
		return llm, modelName, err

	default:
		return nil, "", fmt.Errorf("unknown LLM_PROVIDER %q (use openai or gemini)", provider)
	}
}

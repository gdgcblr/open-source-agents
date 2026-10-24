package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"google.golang.org/genai"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/runner"
)

// traceStep is one line of the investigation audit trail.
type traceStep struct {
	At      string         `json:"at"`
	Kind    string         `json:"kind"` // tool_call | tool_result | answer | error
	Tool    string         `json:"tool,omitempty"`
	Args    map[string]any `json:"args,omitempty"`
	Result  string         `json:"result,omitempty"`
	Text    string         `json:"text,omitempty"`
	Elapsed string         `json:"elapsed"`
}

type runTrace struct {
	Prompt       string      `json:"prompt"`
	Model        string      `json:"model"`
	Started      time.Time   `json:"started"`
	Duration     string      `json:"duration"`
	ToolCalls    int         `json:"tool_calls"`
	InputTokens  int32       `json:"input_tokens"`
	OutputTokens int32       `json:"output_tokens"`
	Steps        []traceStep `json:"steps"`
	Report       string      `json:"report"`
	Error        string      `json:"error,omitempty"`
}

// runTriage runs one investigation without the interactive console: it streams
// each tool call to stderr as it happens, prints the report to stdout, and
// writes the full audit trail to tracePath (if set).
func runTriage(ctx context.Context, a agent.Agent, prompt, modelName, tracePath string, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	r, err := runner.NewInMemory("incident_triage", a)
	if err != nil {
		return err
	}
	tr := &runTrace{Prompt: prompt, Model: modelName, Started: time.Now()}
	log := os.Stderr
	step := func(s traceStep) {
		s.At = time.Now().Format(time.TimeOnly)
		s.Elapsed = time.Since(tr.Started).Round(100 * time.Millisecond).String()
		tr.Steps = append(tr.Steps, s)
	}

	fmt.Fprintf(log, "▶ triage started (model %s, timeout %s)\n", modelName, timeout)
	msg := genai.NewContentFromText(prompt, genai.RoleUser)
	var report strings.Builder
	for ev, err := range r.Run(ctx, "oncall", fmt.Sprintf("triage-%d", time.Now().UnixNano()), msg, agent.RunConfig{}) {
		if err != nil {
			tr.Error = err.Error()
			step(traceStep{Kind: "error", Text: err.Error()})
			break
		}
		if u := ev.UsageMetadata; u != nil {
			tr.InputTokens += u.PromptTokenCount
			tr.OutputTokens += u.CandidatesTokenCount
		}
		if ev.ErrorMessage != "" {
			tr.Error = ev.ErrorMessage
			step(traceStep{Kind: "error", Text: ev.ErrorMessage})
		}
		if ev.Content == nil {
			continue
		}
		for _, p := range ev.Content.Parts {
			switch {
			case p.FunctionCall != nil:
				tr.ToolCalls++
				step(traceStep{Kind: "tool_call", Tool: p.FunctionCall.Name, Args: p.FunctionCall.Args})
				args, _ := json.Marshal(p.FunctionCall.Args)
				fmt.Fprintf(log, "  [%5s] → %s %s\n", time.Since(tr.Started).Round(time.Second), p.FunctionCall.Name, truncate(string(args), 160))
			case p.FunctionResponse != nil:
				res, _ := json.Marshal(p.FunctionResponse.Response)
				step(traceStep{Kind: "tool_result", Tool: p.FunctionResponse.Name, Result: truncate(string(res), 4000)})
				fmt.Fprintf(log, "  [%5s] ← %s (%d bytes)\n", time.Since(tr.Started).Round(time.Second), p.FunctionResponse.Name, len(res))
			case p.Text != "" && !p.Thought && ev.IsFinalResponse():
				report.WriteString(p.Text)
			}
		}
	}
	if ctx.Err() == context.DeadlineExceeded && tr.Error == "" {
		tr.Error = "timed out after " + timeout.String()
	}
	tr.Report = report.String()
	tr.Duration = time.Since(tr.Started).Round(100 * time.Millisecond).String()
	if tr.Report != "" {
		step(traceStep{Kind: "answer", Text: tr.Report})
	}

	fmt.Fprintf(log, "■ done in %s · %d tool calls · %d in / %d out tokens\n", tr.Duration, tr.ToolCalls, tr.InputTokens, tr.OutputTokens)
	if tr.Error != "" {
		fmt.Fprintf(log, "✗ %s\n", tr.Error)
	}
	fmt.Println(tr.Report)

	if tracePath != "" {
		b, _ := json.MarshalIndent(tr, "", "  ")
		err := os.MkdirAll(filepath.Dir(tracePath), 0o755)
		if err == nil {
			err = os.WriteFile(tracePath, b, 0o644)
		}
		if err != nil {
			fmt.Fprintf(log, "could not write trace: %v\n", err)
		} else {
			fmt.Fprintf(log, "trace written to %s\n", tracePath)
		}
	}
	if tr.Error != "" {
		return fmt.Errorf("%s", tr.Error)
	}
	if tr.Report == "" {
		return fmt.Errorf("agent produced no report")
	}
	return nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

// readPrompt returns the args joined, or stdin when no args are given, so an
// alert payload can be piped in.
func readPrompt(args []string) (string, error) {
	if len(args) > 0 {
		return strings.Join(args, " "), nil
	}
	if fi, err := os.Stdin.Stat(); err == nil && fi.Mode()&os.ModeCharDevice != 0 {
		return "Triage the alerts that are firing right now.", nil
	}
	b, err := io.ReadAll(io.LimitReader(os.Stdin, 64<<10))
	if err != nil {
		return "", err
	}
	if s := strings.TrimSpace(string(b)); s != "" {
		return s, nil
	}
	return "Triage the alerts that are firing right now.", nil
}

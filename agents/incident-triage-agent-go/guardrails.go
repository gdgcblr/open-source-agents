package main

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/tool"
)

// Guardrails run as ADK tool callbacks, outside the model's control:
//   - a per-invocation budget on tool calls, so a confused model cannot loop;
//   - query validation, so the model cannot issue unbounded or expensive scans;
//   - redaction of secrets and PII in every tool result before the model sees it.
// The tools themselves are read-only (HTTP GET only), time out after 15s, cap
// response size, window length and number of series.

type guardrails struct {
	maxToolCalls int

	mu    sync.Mutex
	calls map[string]int // invocation ID -> tool calls so far
}

func newGuardrails(maxToolCalls int) *guardrails {
	return &guardrails{maxToolCalls: maxToolCalls, calls: map[string]int{}}
}

// beforeTool enforces the call budget and validates query arguments. A
// non-nil result skips the tool and is returned to the model instead.
func (g *guardrails) beforeTool(ctx agent.Context, t tool.Tool, args map[string]any) (map[string]any, error) {
	g.mu.Lock()
	g.calls[ctx.InvocationID()]++
	n := g.calls[ctx.InvocationID()]
	g.mu.Unlock()
	if n > g.maxToolCalls {
		return map[string]any{"error": fmt.Sprintf(
			"tool budget of %d calls exhausted: stop investigating and write the report with the evidence you have", g.maxToolCalls)}, nil
	}
	if q, ok := args["query"].(string); ok {
		if err := validateQuery(q); err != nil {
			return map[string]any{"error": "query rejected by guardrail: " + err.Error()}, nil
		}
	}
	return nil, nil
}

// afterTool redacts secrets and PII from the tool result.
func (g *guardrails) afterTool(_ agent.Context, _ tool.Tool, _, result map[string]any, err error) (map[string]any, error) {
	if err != nil || result == nil {
		return nil, nil
	}
	return redactValue(result).(map[string]any), nil
}

var (
	rangeSelector = regexp.MustCompile(`\[(\d+)([smhdwy])`)
	matchAll      = regexp.MustCompile(`\{\s*__name__\s*=~\s*"\.[*+]"\s*\}`)
)

const (
	maxQueryLen   = 600
	maxQueryRange = 24 * time.Hour
)

func validateQuery(q string) error {
	if len(q) > maxQueryLen {
		return fmt.Errorf("query longer than %d characters", maxQueryLen)
	}
	if matchAll.MatchString(q) {
		return fmt.Errorf("matching every metric name is not allowed")
	}
	if strings.TrimSpace(q) == "" {
		return fmt.Errorf("empty query")
	}
	unit := map[string]time.Duration{"s": time.Second, "m": time.Minute, "h": time.Hour, "d": 24 * time.Hour, "w": 7 * 24 * time.Hour, "y": 365 * 24 * time.Hour}
	for _, m := range rangeSelector.FindAllStringSubmatch(q, -1) {
		n, _ := strconv.Atoi(m[1])
		if time.Duration(n)*unit[m[2]] > maxQueryRange {
			return fmt.Errorf("range [%s%s] exceeds the %s limit", m[1], m[2], maxQueryRange)
		}
	}
	return nil
}

var redactions = []struct {
	re   *regexp.Regexp
	repl string
}{
	{regexp.MustCompile(`(?i)\b(bearer|token|api[_-]?key|secret|password|passwd|authorization)(["':=\s]+)[^\s"',}]+`), `$1$2[REDACTED]`},
	{regexp.MustCompile(`\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b`), `[REDACTED_JWT]`},
	{regexp.MustCompile(`\b(AKIA|ASIA)[A-Z0-9]{16}\b`), `[REDACTED_AWS_KEY]`},
	{regexp.MustCompile(`\bAIza[0-9A-Za-z_-]{35}\b`), `[REDACTED_GOOGLE_KEY]`},
	{regexp.MustCompile(`\bAQ\.[0-9A-Za-z_-]{30,}`), `[REDACTED_GOOGLE_KEY]`},
	{regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`), `[REDACTED_EMAIL]`},
	{regexp.MustCompile(`\b(?:\d[ -]?){13,19}\b`), `[REDACTED_NUMBER]`},
}

func redact(s string) string {
	for _, r := range redactions {
		s = r.re.ReplaceAllString(s, r.repl)
	}
	return s
}

func redactValue(v any) any {
	switch x := v.(type) {
	case string:
		return redact(x)
	case map[string]any:
		out := make(map[string]any, len(x))
		for k, val := range x {
			out[k] = redactValue(val)
		}
		return out
	case []any:
		out := make([]any, len(x))
		for i, val := range x {
			out[i] = redactValue(val)
		}
		return out
	default:
		return v
	}
}

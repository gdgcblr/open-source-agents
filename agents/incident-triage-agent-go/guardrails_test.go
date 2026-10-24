package main

import (
	"strings"
	"testing"
)

func TestValidateQuery(t *testing.T) {
	tests := []struct {
		name    string
		query   string
		wantErr bool
	}{
		{"rate over 1m", `sum by (service) (rate(http_requests_total[1m]))`, false},
		{"subquery within limit", `avg_over_time((up)[60m:30s] offset 5m)`, false},
		{"one day is the limit", `rate(x[24h])`, false},
		{"empty", "   ", true},
		{"lookback over 24h", `rate(http_requests_total[7d])`, true},
		{"weeks", `max_over_time(up[2w])`, true},
		{"match every metric", `{__name__=~".*"}`, true},
		{"match every metric, plus", `count({__name__ =~ ".+"})`, true},
		{"too long", strings.Repeat("a", maxQueryLen+1), true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateQuery(tt.query)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateQuery(%q) error = %v, wantErr %v", tt.query, err, tt.wantErr)
			}
		})
	}
}

// Key-shaped fixtures are assembled at runtime so no secret-looking literal
// sits in the source (and secret scanners stay quiet).
var (
	fakeGoogleKey    = "AI" + "za" + strings.Repeat("F", 35)
	fakeNewGoogleKey = "AQ" + "." + strings.Repeat("f", 40)
	fakeAWSKey       = "AK" + "IA" + strings.Repeat("Z", 16)
)

func TestRedact(t *testing.T) {
	tests := []struct {
		name, in, leak string
	}{
		{"email", `user alice@example.com failed`, "alice@example.com"},
		{"card number", `charge 4111 1111 1111 1111 declined`, "4111 1111 1111 1111"},
		{"bearer token", `Authorization: Bearer abc.def-123`, "abc.def-123"},
		{"password field", `{"password":"hunter2"}`, "hunter2"},
		{"google key", "key=" + fakeGoogleKey, fakeGoogleKey},
		{"new google key", "GOOGLE_API_KEY=" + fakeNewGoogleKey, fakeNewGoogleKey},
		{"aws key", fakeAWSKey + " in env", fakeAWSKey},
		{"jwt", "token eyJ" + strings.Repeat("a", 20) + ".eyJ" + strings.Repeat("b", 20) + "." + strings.Repeat("c", 20), "eyJ" + strings.Repeat("a", 20)},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := redact(tt.in); strings.Contains(got, tt.leak) {
				t.Errorf("redact(%q) = %q, still contains %q", tt.in, got, tt.leak)
			}
		})
	}
}

func TestRedactKeepsOperationalText(t *testing.T) {
	in := `exchange-rate refresh failed: fx-provider timeout after 3s (p99 2.485s, 20 rps)`
	if got := redact(in); got != in {
		t.Errorf("redact changed harmless text:\n got %q\nwant %q", got, in)
	}
}

func TestRedactValueWalksNestedResults(t *testing.T) {
	in := map[string]any{
		"patterns": []any{
			map[string]any{"sample": "payment for bob@example.com failed", "count": 3},
		},
	}
	out := redactValue(in).(map[string]any)
	sample := out["patterns"].([]any)[0].(map[string]any)["sample"].(string)
	if strings.Contains(sample, "bob@example.com") {
		t.Errorf("nested email not redacted: %q", sample)
	}
	if out["patterns"].([]any)[0].(map[string]any)["count"] != 3 {
		t.Errorf("non-string values must be kept")
	}
}

package main

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	"google.golang.org/adk/v2/agent"
)

// service_health gives the model every service's golden signals in one call,
// each already compared with its baseline, so even a small model never has to
// write PromQL to see what is abnormal. It assumes conventional metric names:
// http_requests_total{code}, http_request_duration_seconds (histogram),
// downstream_request_duration_seconds{target,outcome} (histogram),
// process_resident_memory_bytes, process_start_time_seconds and
// build_info{version}, all carrying a service label.

// signal is one golden-signal reading for a service.
type signal struct {
	Name     string  `json:"signal"`
	Now      float64 `json:"now"`
	Baseline float64 `json:"baseline_median_1h"`
	Verdict  string  `json:"verdict"`
}

type serviceHealth struct {
	Service  string   `json:"service"`
	Version  string   `json:"running_version,omitempty"`
	Restarts int      `json:"restarts_last_30m"`
	Signals  []signal `json:"signals"`
	Abnormal []string `json:"abnormal_signals,omitempty"`
	// NewLogs are WARN/ERROR patterns that are new or increasing versus the
	// previous 5 minutes; steady noise is left out on purpose.
	NewLogs []logPattern `json:"new_or_increasing_log_patterns,omitempty"`
}

type healthOutput struct {
	Now      string            `json:"now"`
	Method   string            `json:"method"`
	Services []serviceHealth   `json:"services"`
	Queries  map[string]string `json:"queries"` // signal -> PromQL, so evidence can be re-run

}

type healthSpec struct {
	name   string
	expr   string  // must aggregate "by (service ...)"
	minAbs float64 // ignore changes while "now" is below this
	// dropIsBad marks signals where a fall is a problem (traffic). For
	// latency, errors and memory a fall is recovery, not an incident.
	dropIsBad bool
}

var healthSpecs = []healthSpec{
	{"requests_per_sec", `sum by (service) (rate(http_requests_total[1m]))`, 0.5, true},
	{"error_ratio_5xx", `(sum by (service) (rate(http_requests_total{code=~"5.."}[1m])) or sum by (service) (rate(http_requests_total[1m])) * 0) / sum by (service) (rate(http_requests_total[1m]))`, 0.01, false},
	{"p99_latency_seconds", `histogram_quantile(0.99, sum by (service, le) (rate(http_request_duration_seconds_bucket[1m])))`, 0.05, false},
	{"memory_rss_mb", `max by (service) (process_resident_memory_bytes) / 1e6`, 1, false},
	{"downstream_p99_seconds", `histogram_quantile(0.99, sum by (service, target, le) (rate(downstream_request_duration_seconds_bucket[1m])))`, 0.05, false},
	{"downstream_error_ratio", `(sum by (service, target) (rate(downstream_request_duration_seconds_count{outcome="error"}[1m])) or sum by (service, target) (rate(downstream_request_duration_seconds_count[1m])) * 0) / sum by (service, target) (rate(downstream_request_duration_seconds_count[1m]))`, 0.01, false},
}

func (t triageTools) serviceHealth(ctx agent.Context, _ noInput) (healthOutput, error) {
	out := healthOutput{
		Now:     clock(time.Now()),
		Queries: map[string]string{},
		Method:  "now = average of the last 2 minutes; baseline = median of the hour before the last 5 minutes, so an incident shorter than ~30 minutes cannot hide in it",
	}
	byService := map[string]*serviceHealth{}
	get := func(svc string) *serviceHealth {
		if h, ok := byService[svc]; ok {
			return h
		}
		h := &serviceHealth{Service: svc}
		byService[svc] = h
		return h
	}

	for _, spec := range healthSpecs {
		out.Queries[spec.name] = spec.expr
		nowRes, err := t.prom.instant(ctx, fmt.Sprintf("avg_over_time((%s)[2m:15s])", spec.expr))
		if err != nil {
			return out, fmt.Errorf("%s: %w", spec.name, err)
		}
		baseRes, err := t.prom.instant(ctx, fmt.Sprintf("quantile_over_time(0.5, (%s)[60m:30s] offset 5m)", spec.expr))
		if err != nil {
			return out, fmt.Errorf("%s: %w", spec.name, err)
		}
		base := map[string]float64{}
		for _, v := range baseRes {
			base[labelKey(v.Metric)] = v.Value.value()
		}
		for _, v := range nowRes {
			now := v.Value.value()
			if math.IsNaN(now) {
				continue
			}
			name := spec.name
			if target := v.Metric["target"]; target != "" {
				name += " (calls to " + target + ")"
			}
			b, ok := base[labelKey(v.Metric)]
			if !ok || math.IsNaN(b) {
				b = now
			}
			sig := signal{Name: name, Now: round(now), Baseline: round(b), Verdict: verdict(now, b, spec.minAbs, spec.dropIsBad)}
			h := get(v.Metric["service"])
			h.Signals = append(h.Signals, sig)
			if sig.Verdict != "normal" {
				h.Abnormal = append(h.Abnormal, name)
			}
		}
	}

	if res, err := t.prom.instant(ctx, `sum by (service) (changes(process_start_time_seconds[30m]))`); err == nil {
		for _, v := range res {
			get(v.Metric["service"]).Restarts = int(v.Value.value())
		}
	}
	if res, err := t.prom.instant(ctx, `build_info`); err == nil {
		for _, v := range res {
			get(v.Metric["service"]).Version = v.Metric["version"]
		}
	}

	if logs, err := t.logPatterns(ctx, logInput{Minutes: 5}); err == nil {
		for _, p := range logs.Patterns {
			if !strings.HasPrefix(p.Trend, "NEW") && !strings.HasPrefix(p.Trend, "INCREASING") {
				continue
			}
			if h := get(p.Service); len(h.NewLogs) < 3 {
				h.NewLogs = append(h.NewLogs, p)
				h.Abnormal = append(h.Abnormal, "log: "+p.Message+" ("+p.Trend+")")
			}
		}
	}

	for _, h := range byService {
		if h.Restarts > 0 {
			h.Abnormal = append(h.Abnormal, fmt.Sprintf("restarted %d time(s)", h.Restarts))
		}
		out.Services = append(out.Services, *h)
	}
	sort.Slice(out.Services, func(i, j int) bool { return out.Services[i].Service < out.Services[j].Service })
	return out, nil
}

// verdict compares a reading with its baseline. Small absolute values are
// never abnormal, so 0.001 -> 0.003 errors does not count as "3x".
func verdict(now, base, minAbs float64, dropIsBad bool) string {
	if now < minAbs && base < minAbs {
		return "normal"
	}
	if base <= 0 || base < minAbs {
		return fmt.Sprintf("ABNORMAL: now %.3g, baseline was near zero", now)
	}
	r := now / base
	switch {
	case r >= 1.5:
		return fmt.Sprintf("ABNORMAL: %.1fx baseline", r)
	case r <= 0.67 && dropIsBad:
		return fmt.Sprintf("ABNORMAL: dropped to %.2fx baseline", r)
	case r <= 0.67:
		return "normal (lower than baseline: improving or recovering)"
	default:
		return "normal"
	}
}

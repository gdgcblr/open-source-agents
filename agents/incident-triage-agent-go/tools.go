package main

import (
	"fmt"
	"math"
	"os"
	"sort"
	"strings"
	"time"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/tool"
	"google.golang.org/adk/v2/tool/functiontool"
)

// Every tool is read-only and returns summaries, not raw datapoints: the Go
// code does the arithmetic so the model only has to reason.

const maxSeries = 10

type triageTools struct {
	prom          promClient
	loki          lokiClient
	baselinesFile string
}

func (t triageTools) all() ([]tool.Tool, error) {
	var tools []tool.Tool
	add := func(tl tool.Tool, err error) error {
		if err != nil {
			return err
		}
		tools = append(tools, tl)
		return nil
	}
	for _, err := range []error{
		add(functiontool.New(functiontool.Config{
			Name:        "get_firing_alerts",
			Description: "Lists alerts that are currently firing or pending in Prometheus, with labels, summary and since when.",
		}, t.firingAlerts)),
		add(functiontool.New(functiontool.Config{
			Name:        "service_health",
			Description: "START HERE. Golden signals for every service (request rate, 5xx error ratio, p99 latency, calls to downstream services, memory, restarts, version), each compared with its median over the previous hour and marked normal or ABNORMAL.",
		}, t.serviceHealth)),
		add(functiontool.New(functiontool.Config{
			Name:        "list_metrics",
			Description: "Lists application metric names available in Prometheus (Go runtime and scrape internals are hidden).",
		}, t.listMetrics)),
		add(functiontool.New(functiontool.Config{
			Name:        "prom_query_summary",
			Description: "Runs a PromQL range query over the last N minutes and returns per-series min/avg/max/last and when the value changed. Use rate() for counters and histogram_quantile() for latency.",
		}, t.promSummary)),
		add(functiontool.New(functiontool.Config{
			Name:        "compare_to_baseline",
			Description: "Compares the recent average of a PromQL expression with the same-length window some minutes earlier, per series. Tells you whether a signal is actually abnormal.",
		}, t.compareToBaseline)),
		add(functiontool.New(functiontool.Config{
			Name:        "log_patterns",
			Description: "Groups WARN/ERROR log lines from Loki by service and message, with counts for the recent window versus the window before it, and a sample line per pattern.",
		}, t.logPatterns)),
		add(functiontool.New(functiontool.Config{
			Name:        "recent_changes",
			Description: "Lists deploys (version label changes in build_info) and process restarts in the last N minutes.",
		}, t.recentChanges)),
		add(functiontool.New(functiontool.Config{
			Name:        "known_baselines",
			Description: "Returns the team's documented steady-state noise: signals that are always present and are not incidents unless they change.",
		}, t.knownBaselines)),
	} {
		if err != nil {
			return nil, err
		}
	}
	return tools, nil
}

func minutesOr(m, def int) time.Duration {
	if m <= 0 {
		m = def
	}
	if m > 24*60 {
		m = 24 * 60
	}
	return time.Duration(m) * time.Minute
}

// --- get_firing_alerts ---

// noInput is for tools without real arguments. It carries one optional field
// because some OpenAI-compatible servers (e.g. Ollama) reject an object schema
// with no properties.
type noInput struct {
	Reason string `json:"reason,omitempty" jsonschema:"optional: why you are calling this tool"`
}

type alertInfo struct {
	Name     string            `json:"name"`
	State    string            `json:"state"`
	Labels   map[string]string `json:"labels"`
	Summary  string            `json:"summary"`
	ActiveAt string            `json:"active_since"`
}

type alertsOutput struct {
	Now    string      `json:"now"`
	Alerts []alertInfo `json:"alerts"`
}

func (t triageTools) firingAlerts(ctx agent.Context, _ noInput) (alertsOutput, error) {
	var data struct {
		Alerts []struct {
			Labels      map[string]string `json:"labels"`
			Annotations map[string]string `json:"annotations"`
			State       string            `json:"state"`
			ActiveAt    time.Time         `json:"activeAt"`
		} `json:"alerts"`
	}
	if err := httpGetJSON(ctx, t.prom.base, "/api/v1/alerts", nil, &data); err != nil {
		return alertsOutput{}, err
	}
	out := alertsOutput{Now: clock(time.Now())}
	for _, a := range data.Alerts {
		out.Alerts = append(out.Alerts, alertInfo{
			Name:     a.Labels["alertname"],
			State:    a.State,
			Labels:   a.Labels,
			Summary:  a.Annotations["summary"],
			ActiveAt: clock(a.ActiveAt),
		})
	}
	return out, nil
}

// --- list_metrics ---

type metricsOutput struct {
	Metrics []string `json:"metrics"`
}

func (t triageTools) listMetrics(ctx agent.Context, _ noInput) (metricsOutput, error) {
	var names []string
	if err := httpGetJSON(ctx, t.prom.base, "/api/v1/label/__name__/values", nil, &names); err != nil {
		return metricsOutput{}, err
	}
	var out metricsOutput
	for _, n := range names {
		if strings.HasPrefix(n, "go_") || strings.HasPrefix(n, "promhttp_") ||
			strings.HasPrefix(n, "scrape_") || strings.HasPrefix(n, "prometheus_") {
			continue
		}
		out.Metrics = append(out.Metrics, n)
	}
	return out, nil
}

// --- prom_query_summary ---

type summaryInput struct {
	Query   string `json:"query" jsonschema:"PromQL expression"`
	Minutes int    `json:"minutes,omitempty" jsonschema:"lookback window in minutes (default 15)"`
}

type seriesSummary struct {
	Labels    string  `json:"labels"`
	Min       float64 `json:"min"`
	Avg       float64 `json:"avg"`
	Max       float64 `json:"max"`
	Last      float64 `json:"last"`
	StartedAt float64 `json:"value_at_window_start"`
	ChangedAt string  `json:"changed_at,omitempty"`
}

type summaryOutput struct {
	Query       string          `json:"query"`
	Window      string          `json:"window"`
	Series      []seriesSummary `json:"series"`
	MoreSeries  int             `json:"more_series_not_shown,omitempty"`
	NoDataCount int             `json:"series_without_data,omitempty"`
}

func (t triageTools) promSummary(ctx agent.Context, in summaryInput) (summaryOutput, error) {
	window := minutesOr(in.Minutes, 15)
	step := max(window/120, 5*time.Second)
	res, err := t.prom.rangeQuery(ctx, in.Query, window, step)
	if err != nil {
		return summaryOutput{}, err
	}
	out := summaryOutput{Query: in.Query, Window: window.String()}
	for _, r := range res {
		var vals []float64
		var times []time.Time
		for _, s := range r.Values {
			if v := s.value(); !math.IsNaN(v) && !math.IsInf(v, 0) {
				vals = append(vals, v)
				times = append(times, s.time())
			}
		}
		if len(vals) == 0 {
			out.NoDataCount++
			continue
		}
		ss := seriesSummary{Labels: labelKey(r.Metric), Min: vals[0], Max: vals[0], Last: vals[len(vals)-1], StartedAt: vals[0]}
		sum := 0.0
		for _, v := range vals {
			ss.Min, ss.Max = math.Min(ss.Min, v), math.Max(ss.Max, v)
			sum += v
		}
		ss.Avg = sum / float64(len(vals))
		if i := changePoint(vals); i >= 0 {
			ss.ChangedAt = clock(times[i])
		}
		ss.Min, ss.Avg, ss.Max, ss.Last, ss.StartedAt = round(ss.Min), round(ss.Avg), round(ss.Max), round(ss.Last), round(ss.StartedAt)
		out.Series = append(out.Series, ss)
	}
	// Most extreme series first, so truncation keeps the interesting ones.
	sort.Slice(out.Series, func(i, j int) bool { return out.Series[i].Max > out.Series[j].Max })
	if len(out.Series) > maxSeries {
		out.MoreSeries = len(out.Series) - maxSeries
		out.Series = out.Series[:maxSeries]
	}
	return out, nil
}

// changePoint returns the first index where the series leaves the band around
// its opening level and stays out for 3 points, or -1.
func changePoint(vals []float64) int {
	if len(vals) < 8 {
		return -1
	}
	head := append([]float64(nil), vals[:len(vals)/4]...)
	sort.Float64s(head)
	base := head[len(head)/2]
	band := math.Max(math.Abs(base)*0.5, 1e-9)
	run := 0
	for i := len(vals) / 4; i < len(vals); i++ {
		if math.Abs(vals[i]-base) > band {
			run++
			if run == 3 {
				return i - 2
			}
		} else {
			run = 0
		}
	}
	return -1
}

// --- compare_to_baseline ---

type baselineInput struct {
	Query                 string `json:"query" jsonschema:"PromQL expression, e.g. a rate() or histogram_quantile()"`
	RecentMinutes         int    `json:"recent_minutes,omitempty" jsonschema:"length of the recent window (default 5)"`
	BaselineOffsetMinutes int    `json:"baseline_offset_minutes,omitempty" jsonschema:"how far back the baseline window starts (default 30)"`
}

type baselineRow struct {
	Labels   string  `json:"labels"`
	Recent   float64 `json:"recent_avg"`
	Baseline float64 `json:"baseline_avg"`
	Ratio    float64 `json:"ratio,omitempty"`
	Verdict  string  `json:"verdict"`
}

type baselineOutput struct {
	RecentQuery   string        `json:"recent_query"`
	BaselineQuery string        `json:"baseline_query"`
	Rows          []baselineRow `json:"series"`
}

func (t triageTools) compareToBaseline(ctx agent.Context, in baselineInput) (baselineOutput, error) {
	recent := minutesOr(in.RecentMinutes, 5)
	offset := minutesOr(in.BaselineOffsetMinutes, 30)
	r := fmt.Sprintf("avg_over_time((%s)[%dm:15s])", in.Query, int(recent.Minutes()))
	b := fmt.Sprintf("avg_over_time((%s)[%dm:15s] offset %dm)", in.Query, int(recent.Minutes()), int(offset.Minutes()))
	out := baselineOutput{RecentQuery: r, BaselineQuery: b}

	nowRes, err := t.prom.instant(ctx, r)
	if err != nil {
		return out, err
	}
	baseRes, err := t.prom.instant(ctx, b)
	if err != nil {
		return out, err
	}
	base := map[string]float64{}
	for _, v := range baseRes {
		base[labelKey(v.Metric)] = v.Value.value()
	}
	for _, v := range nowRes {
		key := labelKey(v.Metric)
		row := baselineRow{Labels: key, Recent: v.Value.value()}
		bv, ok := base[key]
		switch {
		case math.IsNaN(row.Recent):
			continue
		case !ok || math.IsNaN(bv):
			row.Verdict = "new: no baseline data"
		case bv == 0 && row.Recent == 0:
			row.Verdict = "normal"
		case bv == 0:
			row.Verdict = "new: was zero at baseline"
		default:
			row.Ratio = round(row.Recent / bv)
			switch {
			case row.Ratio > 1.5:
				row.Verdict = fmt.Sprintf("ABNORMAL: %.1fx baseline", row.Ratio)
			case row.Ratio < 0.67:
				row.Verdict = fmt.Sprintf("ABNORMAL: dropped to %.1fx baseline", row.Ratio)
			default:
				row.Verdict = "normal"
			}
			row.Baseline = round(bv)
		}
		row.Recent = round(row.Recent)
		out.Rows = append(out.Rows, row)
		if len(out.Rows) == maxSeries {
			break
		}
	}
	return out, nil
}

// --- log_patterns ---

type logInput struct {
	Service string `json:"service,omitempty" jsonschema:"service label to filter on; empty means all services"`
	Minutes int    `json:"minutes,omitempty" jsonschema:"recent window in minutes (default 10); the baseline is the window before it"`
}

type logPattern struct {
	Service  string `json:"service"`
	Level    string `json:"level"`
	Message  string `json:"message"`
	Recent   float64 `json:"recent_per_min"`
	Previous float64 `json:"previous_window_per_min"`
	Trend    string `json:"trend"`
	Sample   string `json:"sample,omitempty"`
}

type logOutput struct {
	Query    string       `json:"logql"`
	Window   string       `json:"window"`
	Patterns []logPattern `json:"patterns"`
}

func (t triageTools) logPatterns(ctx agent.Context, in logInput) (logOutput, error) {
	window := minutesOr(in.Minutes, 10)
	sel := `{service=~".+", level=~"ERROR|WARN"}`
	if in.Service != "" {
		sel = fmt.Sprintf(`{service=%q, level=~"ERROR|WARN"}`, in.Service)
	}
	m := int(window.Minutes())
	q := fmt.Sprintf(`sum by (service, level, msg) (count_over_time(%s | json msg="msg" [%dm]))`, sel, m)
	prevQ := fmt.Sprintf(`sum by (service, level, msg) (count_over_time(%s | json msg="msg" [%dm] offset %dm))`, sel, m, m)
	out := logOutput{Query: q, Window: window.String()}

	now, err := t.loki.instant(ctx, q)
	if err != nil {
		return out, err
	}
	prev, err := t.loki.instant(ctx, prevQ)
	if err != nil {
		return out, err
	}
	prevCount := map[string]int{}
	for _, v := range prev {
		prevCount[labelKey(v.Metric)] = int(v.Value.value())
	}
	for _, v := range now {
		p := logPattern{
			Service:  v.Metric["service"],
			Level:    v.Metric["level"],
			Message:  v.Metric["msg"],
			Recent:   round(v.Value.value() / float64(m)),
			Previous: round(float64(prevCount[labelKey(v.Metric)]) / float64(m)),
		}
		switch {
		case p.Previous == 0:
			p.Trend = "NEW in this window"
		case p.Recent > 1.5*p.Previous:
			p.Trend = fmt.Sprintf("INCREASING %.1fx", p.Recent/p.Previous)
		case p.Recent < 0.67*p.Previous:
			p.Trend = "decreasing"
		default:
			p.Trend = "steady (same as previous window)"
		}
		out.Patterns = append(out.Patterns, p)
	}
	sort.Slice(out.Patterns, func(i, j int) bool { return out.Patterns[i].Recent > out.Patterns[j].Recent })
	if len(out.Patterns) > 15 {
		out.Patterns = out.Patterns[:15]
	}

	// One sample line per pattern, so the model sees real fields.
	streams, err := t.loki.lines(ctx, sel, window, 500)
	if err == nil {
		for _, s := range streams {
			for _, v := range s.Values {
				for i := range out.Patterns {
					p := &out.Patterns[i]
					if p.Sample == "" && p.Service == s.Stream["service"] && strings.Contains(v[1], `"msg":"`+p.Message+`"`) {
						if len(v[1]) > 300 {
							v[1] = v[1][:300]
						}
						p.Sample = v[1]
					}
				}
			}
		}
	}
	return out, nil
}

// --- recent_changes ---

type changesInput struct {
	Minutes int `json:"minutes,omitempty" jsonschema:"lookback window in minutes (default 30)"`
}

type change struct {
	Time   string `json:"time"`
	Kind   string `json:"kind"`
	Detail string `json:"detail"`
}

type changesOutput struct {
	Window  string   `json:"window"`
	Changes []change `json:"changes"`
	Note    string   `json:"note,omitempty"`
}

func (t triageTools) recentChanges(ctx agent.Context, in changesInput) (changesOutput, error) {
	window := minutesOr(in.Minutes, 30)
	step := 15 * time.Second
	out := changesOutput{Window: window.String()}

	// A deploy is a service whose build_info version label changes inside the
	// window. A new process with the same version is a restart, not a deploy.
	res, err := t.prom.rangeQuery(ctx, "build_info", window, step)
	if err != nil {
		return out, err
	}
	type span struct {
		version     string
		first, last time.Time
	}
	byService := map[string][]span{}
	for _, r := range res {
		if len(r.Values) == 0 {
			continue
		}
		svc := r.Metric["service"]
		byService[svc] = append(byService[svc], span{r.Metric["version"], r.Values[0].time(), r.Values[len(r.Values)-1].time()})
	}
	for svc, spans := range byService {
		sort.Slice(spans, func(i, j int) bool { return spans[i].first.Before(spans[j].first) })
		for i := 1; i < len(spans); i++ {
			if spans[i].version == spans[i-1].version {
				continue
			}
			out.Changes = append(out.Changes, change{
				Time: clock(spans[i].first), Kind: "deploy",
				Detail: fmt.Sprintf("%s changed version %s -> %s", svc, spans[i-1].version, spans[i].version),
			})
		}
	}

	restarts, err := t.prom.instant(ctx, fmt.Sprintf("changes(process_start_time_seconds[%dm]) > 0", int(window.Minutes())))
	if err != nil {
		return out, err
	}
	for _, r := range restarts {
		out.Changes = append(out.Changes, change{
			Time: "within window", Kind: "restart",
			Detail: fmt.Sprintf("%s process restarted %d time(s)", r.Metric["service"], int(r.Value.value())),
		})
	}
	sort.Slice(out.Changes, func(i, j int) bool { return out.Changes[i].Time < out.Changes[j].Time })
	if len(out.Changes) == 0 {
		out.Note = "no version changes or restarts in the window"
	}
	return out, nil
}

// --- known_baselines ---

type baselinesOutput struct {
	Baselines string `json:"baselines"`
}

func (t triageTools) knownBaselines(_ agent.Context, _ noInput) (baselinesOutput, error) {
	b, err := os.ReadFile(t.baselinesFile)
	if err != nil {
		return baselinesOutput{Baselines: "no baselines file configured"}, nil
	}
	return baselinesOutput{Baselines: string(b)}, nil
}

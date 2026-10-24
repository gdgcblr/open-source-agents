package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

// httpGetJSON performs a read-only GET and decodes the standard
// {"status": ..., "data": ...} envelope used by both Prometheus and Loki.
func httpGetJSON(ctx context.Context, base, path string, params url.Values, data any) error {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, base+path+"?"+params.Encode(), nil)
	if err != nil {
		return err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return err
	}
	var env struct {
		Status string          `json:"status"`
		Error  string          `json:"error"`
		Data   json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &env); err != nil {
		return fmt.Errorf("%s %s: HTTP %d: %.200s", base, path, resp.StatusCode, body)
	}
	if env.Status != "success" {
		return fmt.Errorf("query failed: %s", env.Error)
	}
	return json.Unmarshal(env.Data, data)
}

type sample [2]any // [unix seconds, "value"]

func (s sample) value() float64 {
	str, _ := s[1].(string)
	v, err := strconv.ParseFloat(str, 64)
	if err != nil {
		return math.NaN()
	}
	return v
}

func (s sample) time() time.Time {
	f, _ := s[0].(float64)
	return time.Unix(int64(f), 0)
}

type vectorResult struct {
	Metric map[string]string `json:"metric"`
	Value  sample            `json:"value"`
}

type matrixResult struct {
	Metric map[string]string `json:"metric"`
	Values []sample          `json:"values"`
}

type promClient struct{ base string }

func (p promClient) instant(ctx context.Context, query string) ([]vectorResult, error) {
	var data struct {
		Result []vectorResult `json:"result"`
	}
	err := httpGetJSON(ctx, p.base, "/api/v1/query", url.Values{"query": {query}}, &data)
	return data.Result, err
}

func (p promClient) rangeQuery(ctx context.Context, query string, window, step time.Duration) ([]matrixResult, error) {
	end := time.Now()
	var data struct {
		Result []matrixResult `json:"result"`
	}
	err := httpGetJSON(ctx, p.base, "/api/v1/query_range", url.Values{
		"query": {query},
		"start": {strconv.FormatInt(end.Add(-window).Unix(), 10)},
		"end":   {strconv.FormatInt(end.Unix(), 10)},
		"step":  {strconv.Itoa(int(step.Seconds()))},
	}, &data)
	return data.Result, err
}

type lokiClient struct{ base string }

func (l lokiClient) instant(ctx context.Context, query string) ([]vectorResult, error) {
	var data struct {
		Result []vectorResult `json:"result"`
	}
	err := httpGetJSON(ctx, l.base, "/loki/api/v1/query", url.Values{
		"query": {query},
		"time":  {strconv.FormatInt(time.Now().UnixNano(), 10)},
	}, &data)
	return data.Result, err
}

type logStream struct {
	Stream map[string]string `json:"stream"`
	Values [][2]string       `json:"values"`
}

func (l lokiClient) lines(ctx context.Context, query string, window time.Duration, limit int) ([]logStream, error) {
	end := time.Now()
	var data struct {
		Result []logStream `json:"result"`
	}
	err := httpGetJSON(ctx, l.base, "/loki/api/v1/query_range", url.Values{
		"query":     {query},
		"start":     {strconv.FormatInt(end.Add(-window).UnixNano(), 10)},
		"end":       {strconv.FormatInt(end.UnixNano(), 10)},
		"limit":     {strconv.Itoa(limit)},
		"direction": {"backward"},
	}, &data)
	return data.Result, err
}

// labelKey renders a label set deterministically, without __name__.
func labelKey(m map[string]string) string {
	keys := make([]string, 0, len(m))
	for k := range m {
		if k != "__name__" {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	parts := make([]string, len(keys))
	for i, k := range keys {
		parts[i] = k + "=" + strconv.Quote(m[k])
	}
	return "{" + strings.Join(parts, ", ") + "}"
}

func round(v float64) float64 {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return v
	}
	if math.Abs(v) >= 100 {
		return math.Round(v)
	}
	return math.Round(v*1000) / 1000
}

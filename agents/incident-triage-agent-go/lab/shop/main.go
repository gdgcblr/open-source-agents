// Command shop is a tiny two-service demo shop (checkout -> payments) used as
// the incident lab for the triage agent. Each instance exposes Prometheus
// metrics, pushes JSON logs to Loki, and accepts fault injection on /chaos so
// every incident has a known root cause.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math/rand/v2"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	requests = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "http_requests_total",
		Help: "HTTP requests served, by route and status code.",
	}, []string{"route", "code"})
	duration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "http_request_duration_seconds",
		Help:    "HTTP request latency.",
		Buckets: []float64{.01, .025, .05, .1, .25, .5, 1, 2.5, 5},
	}, []string{"route"})
	downstreamDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "downstream_request_duration_seconds",
		Help:    "Latency of calls to downstream services.",
		Buckets: []float64{.01, .025, .05, .1, .25, .5, 1, 2.5, 5},
	}, []string{"target", "outcome"})
	buildInfo = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "build_info",
		Help: "Always 1; the version label shows what is deployed.",
	}, []string{"version"})
	jobErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "background_job_errors_total",
		Help: "Errors from background jobs.",
	}, []string{"job"})
)

// faults is the injectable state. Pointer fields in a /chaos request mean
// "only change what was sent".
type faults struct {
	LatencyMs    int     `json:"latency_ms"`
	ErrorRate    float64 `json:"error_rate"`
	ErrorCode    int     `json:"error_code"`
	ErrorMsg     string  `json:"error_msg"`
	LeakKBPerReq int     `json:"leak_kb_per_req"`
}

type chaosRequest struct {
	LatencyMs    *int     `json:"latency_ms"`
	ErrorRate    *float64 `json:"error_rate"`
	ErrorCode    *int     `json:"error_code"`
	ErrorMsg     *string  `json:"error_msg"`
	LeakKBPerReq *int     `json:"leak_kb_per_req"`
	Version      *string  `json:"version"`
}

type server struct {
	service    string
	downstream string
	client     *http.Client
	log        *slog.Logger

	mu      sync.Mutex
	f       faults
	version string
	leaked  [][]byte
}

func main() {
	service := env("SERVICE", "checkout")
	port := env("PORT", "8080")

	var out io.Writer = os.Stdout
	if lokiURL := os.Getenv("LOKI_URL"); lokiURL != "" {
		out = io.MultiWriter(os.Stdout, newLokiWriter(lokiURL, service))
	}

	s := &server{
		service:    service,
		downstream: os.Getenv("DOWNSTREAM_URL"),
		client:     &http.Client{Timeout: 3 * time.Second},
		log:        slog.New(slog.NewJSONHandler(out, nil)).With("service", service),
	}
	s.setVersion(env("VERSION", "v1.3.0"))

	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	mux.HandleFunc("/chaos", s.handleChaos)
	mux.HandleFunc("/chaos/reset", s.handleReset)
	switch service {
	case "checkout":
		mux.HandleFunc("/checkout", s.instrument("/checkout", s.handleCheckout))
	case "payments":
		mux.HandleFunc("/pay", s.instrument("/pay", s.handlePay))
	}

	if rps := envInt("LOAD_RPS", 0); rps > 0 {
		go s.generateLoad("http://localhost:"+port+"/checkout", rps)
	}
	if n := envInt("NOISE_PER_SEC", 0); n > 0 {
		go s.backgroundNoise(n)
	}

	s.log.Info("service started", "port", port, "version", s.version)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		s.log.Error("server stopped", "err", err)
		os.Exit(1)
	}
}

// statusError lets a handler pick the status code it fails with.
type statusError struct {
	code int
	msg  string
}

func (e statusError) Error() string { return e.msg }

func (s *server) instrument(route string, h func(*http.Request) error) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		code := http.StatusOK
		if err := h(r); err != nil {
			code = http.StatusInternalServerError
			if se, ok := err.(statusError); ok {
				code = se.code
			}
			http.Error(w, err.Error(), code)
		}
		requests.WithLabelValues(route, strconv.Itoa(code)).Inc()
		duration.WithLabelValues(route).Observe(time.Since(start).Seconds())
	}
}

// applyFaults runs the injected latency, leak and error roll for one request.
func (s *server) applyFaults() error {
	s.mu.Lock()
	f := s.f
	if f.LeakKBPerReq > 0 {
		b := make([]byte, f.LeakKBPerReq*1024)
		for i := 0; i < len(b); i += 4096 {
			b[i] = 1 // touch every page so it counts against the memory limit
		}
		s.leaked = append(s.leaked, b)
	}
	s.mu.Unlock()

	if f.LatencyMs > 0 {
		time.Sleep(time.Duration(f.LatencyMs) * time.Millisecond)
	}
	if f.ErrorRate > 0 && rand.Float64() < f.ErrorRate {
		s.log.Error(f.ErrorMsg, "code", f.ErrorCode)
		return statusError{code: f.ErrorCode, msg: f.ErrorMsg}
	}
	return nil
}

func (s *server) handleCheckout(r *http.Request) error {
	time.Sleep(time.Duration(5+rand.IntN(10)) * time.Millisecond)
	if err := s.applyFaults(); err != nil {
		return err
	}

	start := time.Now()
	resp, err := s.client.Get(s.downstream + "/pay")
	outcome := "ok"
	switch {
	case err != nil:
		outcome = "error"
	case resp.StatusCode >= 500:
		outcome = "error"
	case resp.StatusCode >= 400:
		outcome = "rejected"
	}
	downstreamDuration.WithLabelValues("payments", outcome).Observe(time.Since(start).Seconds())

	if err != nil {
		s.log.Error("payment call failed", "err", err.Error())
		return statusError{code: http.StatusBadGateway, msg: "payment call failed"}
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return statusError{code: resp.StatusCode, msg: "payment not accepted"}
	}
	return nil
}

func (s *server) handlePay(r *http.Request) error {
	time.Sleep(time.Duration(20+rand.IntN(40)) * time.Millisecond)
	if err := s.applyFaults(); err != nil {
		return err
	}
	if rand.Float64() < 0.01 {
		s.log.Warn("card declined", "reason", "insufficient_funds")
		return statusError{code: http.StatusPaymentRequired, msg: "card declined"}
	}
	return nil
}

func (s *server) handleChaos(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		var req chaosRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		s.mu.Lock()
		if req.LatencyMs != nil {
			s.f.LatencyMs = *req.LatencyMs
		}
		if req.ErrorRate != nil {
			s.f.ErrorRate = *req.ErrorRate
		}
		if req.ErrorCode != nil {
			s.f.ErrorCode = *req.ErrorCode
		}
		if req.ErrorMsg != nil {
			s.f.ErrorMsg = *req.ErrorMsg
		}
		if req.LeakKBPerReq != nil {
			s.f.LeakKBPerReq = *req.LeakKBPerReq
		}
		s.mu.Unlock()
		if req.Version != nil {
			s.setVersion(*req.Version)
		}
	}
	s.writeState(w)
}

func (s *server) handleReset(w http.ResponseWriter, _ *http.Request) {
	s.mu.Lock()
	s.f = faults{}
	s.leaked = nil
	s.mu.Unlock()
	s.writeState(w)
}

func (s *server) writeState(w http.ResponseWriter) {
	s.mu.Lock()
	state := struct {
		Service string `json:"service"`
		Version string `json:"version"`
		faults
	}{s.service, s.version, s.f}
	s.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(state)
}

// setVersion simulates a deploy: the build_info label flips and a log line
// records the rollout, like a real deploy event would.
func (s *server) setVersion(v string) {
	s.mu.Lock()
	prev := s.version
	s.version = v
	s.mu.Unlock()
	if prev == v {
		return
	}
	buildInfo.Reset()
	buildInfo.WithLabelValues(v).Set(1)
	if prev != "" {
		s.log.Info("deployment rolled out", "version", v, "previous_version", prev)
	}
}

func (s *server) generateLoad(url string, rps int) {
	client := &http.Client{Timeout: 10 * time.Second}
	for range time.Tick(time.Second / time.Duration(rps)) {
		go func() {
			resp, err := client.Get(url)
			if err == nil {
				io.Copy(io.Discard, resp.Body)
				resp.Body.Close()
			}
		}()
	}
}

// backgroundNoise is a loud, always-on failure that is never the root cause:
// the lab's built-in red herring.
func (s *server) backgroundNoise(perSec int) {
	for range time.Tick(time.Second / time.Duration(perSec)) {
		jobErrors.WithLabelValues("fx_rate_refresh").Inc()
		s.log.Error("exchange-rate refresh failed", "job", "fx_rate_refresh", "err", "fx-provider timeout after 3s")
	}
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	v, err := strconv.Atoi(os.Getenv(key))
	if err != nil {
		return def
	}
	return v
}

// lokiWriter receives one JSON log line per Write (slog's JSONHandler writes
// each record in a single call) and pushes them to Loki in 1s batches.
type lokiWriter struct {
	url     string
	service string
	lines   chan logLine
}

type logLine struct {
	ts   int64
	line []byte
}

func newLokiWriter(url, service string) *lokiWriter {
	lw := &lokiWriter{url: url + "/loki/api/v1/push", service: service, lines: make(chan logLine, 10000)}
	go lw.run()
	return lw
}

func (lw *lokiWriter) Write(p []byte) (int, error) {
	select {
	case lw.lines <- logLine{time.Now().UnixNano(), append([]byte(nil), p...)}:
	default: // drop rather than block the request path
	}
	return len(p), nil
}

func (lw *lokiWriter) run() {
	client := &http.Client{Timeout: 5 * time.Second}
	type stream struct {
		Stream map[string]string `json:"stream"`
		Values [][2]string       `json:"values"`
	}
	for range time.Tick(time.Second) {
		byLevel := map[string]*stream{}
	drain:
		for {
			select {
			case l := <-lw.lines:
				var rec struct {
					Level string `json:"level"`
				}
				json.Unmarshal(l.line, &rec)
				st, ok := byLevel[rec.Level]
				if !ok {
					st = &stream{Stream: map[string]string{"service": lw.service, "level": rec.Level}}
					byLevel[rec.Level] = st
				}
				st.Values = append(st.Values, [2]string{strconv.FormatInt(l.ts, 10), string(bytes.TrimSpace(l.line))})
			default:
				break drain
			}
		}
		if len(byLevel) == 0 {
			continue
		}
		var body struct {
			Streams []*stream `json:"streams"`
		}
		for _, st := range byLevel {
			body.Streams = append(body.Streams, st)
		}
		payload, _ := json.Marshal(body)
		resp, err := client.Post(lw.url, "application/json", bytes.NewReader(payload))
		if err != nil {
			fmt.Fprintln(os.Stderr, "loki push failed:", err)
			continue
		}
		resp.Body.Close()
	}
}

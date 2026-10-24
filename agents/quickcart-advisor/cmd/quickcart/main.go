// Command quickcart is the QuickCart Advisor CLI: it compares one product
// across Swiggy Instamart, Blinkit, Zepto and Amazon India and recommends
// where to buy by total delivered cost, fees, ETA and memberships.
//
// One-shot mode (a product via --url/--query plus --pincode, or --compare)
// sends a single comparison request and prints the agent's final reply;
// without those flags it runs a simple stdin REPL. All prices are integer
// paise, and every offer the agent reports is labeled "qbuys-live" when it
// came from the optional live qbuys adapter or "offline-demo-catalog" when it
// came from the bundled demo data — the demo catalog is the default
// (--offline-demo=true) and demo numbers are never presented as live prices.
//
// Flags fall back to environment variables: LLM_BACKEND, OPENAI_MODEL,
// OPENAI_BASE_URL, OPENAI_API_KEY, QBUYS_BASE_URL. Defaults target a local
// LM Studio server (OpenAI Chat Completions API) on port 1235.
package main

import (
	"bufio"
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"regexp"
	"strings"
	"syscall"

	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/agent"
	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/tools"
)

// envDefault returns the flag default for name: the environment value when
// set, otherwise fallback.
func envDefault(name, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		return v
	}
	return fallback
}

// envDefaultBool returns the flag default for name parsed as a boolean when the
// environment variable is set ("1", "true", "yes", "on" -> true; "0", "false",
// "no", "off" -> false, case-insensitive); otherwise fallback.
func envDefaultBool(name string, fallback bool) bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(name))) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

var pincodeRe = regexp.MustCompile(`^\d{6}$`)

func main() {
	var (
		backend      = flag.String("backend", envDefault("LLM_BACKEND", "openai"), `LLM backend: "openai" (OpenAI-compatible Chat Completions, e.g. LM Studio) or "gemini" (Google Gemini API)`)
		modelName    = flag.String("model", envDefault("OPENAI_MODEL", "google/gemma-4-12b"), `model name on the backend`)
		baseURL      = flag.String("base-url", envDefault("OPENAI_BASE_URL", "http://localhost:1235/v1"), `base URL of the OpenAI-compatible server (openai backend only)`)
		apiKey       = flag.String("api-key", envDefault("OPENAI_API_KEY", "local"), `API key for the backend (any non-empty value works for local servers)`)
		qbuysBaseURL = flag.String("qbuys-base-url", envDefault("QBUYS_BASE_URL", ""), `base URL of the optional qbuys live offers service; empty = offline demo catalog only (demo server e.g. http://localhost:8080)`)
		offlineDemo  = flag.Bool("offline-demo", envDefaultBool("OFFLINE_DEMO", true), `always use the bundled offline demo catalog for all four retailers (default true for demos); set false with --qbuys-base-url to opt into live qbuys data`)
		productURL   = flag.String("url", "", `retailer product URL to compare (Instamart, Blinkit, Zepto or Amazon India)`)
		query        = flag.String("query", "", `free-text product description to compare, e.g. "Amul Taaza milk 1L"`)
		pincode      = flag.String("pincode", "", `6-digit Indian delivery PIN code; required for one-shot comparison`)
		compare      = flag.Bool("compare", false, `force one-shot comparison mode (requires --url or --query, and --pincode)`)
	)
	flag.Parse()

	if err := run(context.Background(), cliConfig{
		backend:      strings.TrimSpace(*backend),
		modelName:    strings.TrimSpace(*modelName),
		baseURL:      strings.TrimSpace(*baseURL),
		apiKey:       strings.TrimSpace(*apiKey),
		qbuysBaseURL: strings.TrimSpace(*qbuysBaseURL),
		offlineDemo:  *offlineDemo,
		productURL:   strings.TrimSpace(*productURL),
		query:        strings.TrimSpace(*query),
		pincode:      strings.TrimSpace(*pincode),
		compare:      *compare,
	}, os.Stdin, os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "quickcart: %v\n", err)
		os.Exit(1)
	}
}

// cliConfig is the resolved command-line configuration.
type cliConfig struct {
	backend      string
	modelName    string
	baseURL      string
	apiKey       string
	qbuysBaseURL string
	offlineDemo  bool
	productURL   string
	query        string
	pincode      string
	compare      bool
}

// product returns whichever product reference the user supplied; a URL wins
// over free text.
func (c cliConfig) product() string {
	if c.productURL != "" {
		return c.productURL
	}
	return c.query
}

// oneShot reports whether the run is a single comparison request: --compare
// forces it; otherwise a product plus a pincode implies it.
func (c cliConfig) oneShot() bool {
	return c.compare || (c.product() != "" && c.pincode != "")
}

func run(ctx context.Context, cfg cliConfig, in io.Reader, out io.Writer) error {
	ctx, stop := signal.NotifyContext(ctx, os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := cfg.validate(); err != nil {
		return err
	}
	applyBackendDefaults(&cfg)

	printStartup(out, cfg)

	deps := tools.NewDeps(cfg.qbuysBaseURL, !cfg.offlineDemo)
	app, err := agent.New(ctx, agent.Config{
		Backend:      cfg.backend,
		ModelName:    cfg.modelName,
		BaseURL:      cfg.baseURL,
		APIKey:       cfg.apiKey,
		QBuysBaseURL: cfg.qbuysBaseURL,
	}, deps)
	if err != nil {
		return fmt.Errorf("build agent: %w", err)
	}

	if cfg.oneShot() {
		msg := fmt.Sprintf("Compare this product across retailers. Product: %s. Delivery PIN: %s.", cfg.product(), cfg.pincode)
		reply, err := app.RunOnce(ctx, msg)
		if err != nil {
			return fmt.Errorf("comparison failed: %w", err)
		}
		fmt.Fprintln(out, reply)
		return nil
	}
	return repl(ctx, app, in, out)
}

// validate checks CLI flag combinations and the pincode format.
func (c cliConfig) validate() error {
	switch strings.ToLower(c.backend) {
	case "openai", "gemini", "":
	default:
		return fmt.Errorf("unknown --backend %q (want %q or %q)", c.backend, "openai", "gemini")
	}
	if c.pincode != "" && !pincodeRe.MatchString(c.pincode) {
		return fmt.Errorf("invalid --pincode %q: must be exactly 6 digits", c.pincode)
	}
	if c.compare && c.product() == "" {
		return errors.New("--compare needs --url or --query identifying the product")
	}
	if c.compare && c.pincode == "" {
		return errors.New("--compare needs --pincode (6-digit delivery PIN)")
	}
	if c.product() != "" && c.pincode == "" {
		return errors.New("--url/--query needs --pincode for a comparison; run without them for an interactive session")
	}
	return nil
}

// applyBackendDefaults swaps model/base-URL defaults in when the user picked
// the Gemini backend without overriding the OpenAI-shaped defaults, so the
// documented "--backend gemini works out of the box" behaviour holds. Values
// that came from the environment or flags are left untouched.
func applyBackendDefaults(cfg *cliConfig) {
	if strings.ToLower(cfg.backend) != "gemini" {
		return
	}
	if cfg.modelName == "google/gemma-4-12b" && strings.TrimSpace(os.Getenv("OPENAI_MODEL")) == "" {
		cfg.modelName = "gemini-flash-latest"
	}
	if cfg.baseURL == "http://localhost:1235/v1" && strings.TrimSpace(os.Getenv("OPENAI_BASE_URL")) == "" {
		cfg.baseURL = ""
	}
}

// printStartup announces the effective backend so the data-provenance story
// is visible before any answer.
func printStartup(out io.Writer, cfg cliConfig) {
	displayBase := cfg.baseURL
	if displayBase == "" {
		displayBase = "(backend default)"
	}
	mode := "offline-demo-catalog (always-on)"
	qbuysDisplay := cfg.qbuysBaseURL
	if !cfg.offlineDemo && cfg.qbuysBaseURL != "" {
		mode = "live qbuys adapter over the offline demo catalog"
	} else {
		qbuysDisplay = "(disabled)"
	}
	fmt.Fprintf(out, "QuickCart Advisor — backend=%s model=%s base-url=%s qbuys=%s data=%s\n", cfg.backend, cfg.modelName, displayBase, qbuysDisplay, mode)
	fmt.Fprintln(out, `Every offer is labeled by data source: "qbuys-live" = live qbuys service (opt-in); "offline-demo-catalog" = bundled demo data (never live prices).`)
}

// repl is the interactive fallback: one agent reply per input line.
func repl(ctx context.Context, app *agent.App, in io.Reader, out io.Writer) error {
	fmt.Fprintln(out, "Interactive mode — describe a product and delivery PIN to compare retailers. Empty line or Ctrl-D/Ctrl-C to exit.")
	fmt.Fprint(out, "> ")

	sc := bufio.NewScanner(in)
	sc.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			return nil
		}
		reply, err := app.RunOnce(ctx, line)
		if err != nil {
			if ctx.Err() != nil {
				return nil // interrupted; exit quietly
			}
			return fmt.Errorf("agent run failed: %w", err)
		}
		fmt.Fprintln(out, reply)
		fmt.Fprint(out, "> ")
	}
	if err := sc.Err(); err != nil {
		return fmt.Errorf("read input: %w", err)
	}
	return nil
}

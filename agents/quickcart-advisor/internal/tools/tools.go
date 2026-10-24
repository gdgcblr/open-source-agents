// Package tools exposes the agent's five function tools as thin ADK
// functiontool wrappers. All computation happens in internal/retailers and
// internal/qbuys — the handlers here only adapt agent.Context calls to those
// packages. The LLM decides which tools to call; it never computes prices,
// totals, or rankings itself.
package tools

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"time"

	"google.golang.org/adk/v2/agent"
	"google.golang.org/adk/v2/tool"
	"google.golang.org/adk/v2/tool/functiontool"

	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/qbuys"
	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/retailers"
)

// Deps carries the collaborators the tool handlers need. Construct it with
// NewDeps for production, or hand-build it in tests.
type Deps struct {
	Composite *retailers.Composite
	Catalog   retailers.CatalogSource
	Live      *qbuys.Source
	Now       func() time.Time // nil means time.Now
}

// NewDeps wires the dependency stack. The bundled offline demo catalog is
// always present and serves all four retailers. Live qbuys data is opt-in: a
// nil live source is used unless enableLive is requested AND qbuysBaseURL is
// non-empty — so by default every offer is a deterministic offline-demo offer
// with no network calls. Amazon is always catalog-sourced regardless.
func NewDeps(qbuysBaseURL string, enableLive bool) *Deps {
	catalog := retailers.CatalogSource{}
	// Live is a DataSource interface: assign a typed nil only through the
	// interface so "no live source" is a genuine nil (a typed *qbuys.Source
	// nil would make the interface non-nil and panic on method calls).
	var live *qbuys.Source
	var liveSrc retailers.DataSource
	if enableLive && strings.TrimSpace(qbuysBaseURL) != "" {
		live = qbuys.NewSource(qbuys.NewClient(qbuysBaseURL))
		liveSrc = live
	}
	return &Deps{
		Composite: retailers.NewComposite(liveSrc, catalog),
		Catalog:   catalog,
		Live:      live,
	}
}

func (d *Deps) now() time.Time {
	if d != nil && d.Now != nil {
		return d.Now().UTC()
	}
	return time.Now().UTC()
}

// ---- identify_product ----

// IdentifyArgs are the inputs of the identify_product tool.
type IdentifyArgs struct {
	InputURL  string `json:"input_url,omitempty"`
	InputText string `json:"input_text,omitempty"`
}

// IdentifyResult is the resolve output: a normalized Product plus honesty
// metadata about how confident the match is and where it came from.
type IdentifyResult struct {
	Found           bool               `json:"found"`
	Product         *retailers.Product `json:"product,omitempty"`
	MatchConfidence float64            `json:"match_confidence"`
	Platform        string             `json:"platform,omitempty"` // inferred from URL when present
	Note            string             `json:"note"`
}

var urlHostRe = regexp.MustCompile(`^[a-z0-9.-]+\.[a-z]{2,}(/|$)`)

// allowedRetailHosts maps each supported retailer's owned hostnames (exact
// host or subdomain) to its platform id. Matching is strict — a look-alike
// domain that merely *contains* the brand (e.g. "swiggy-deals.example.com") is
// NOT treated as a retailer; this is the only URL trust decision the agent
// makes, and it never follows the URL.
var allowedRetailHosts = map[string]string{
	"swiggy.com":   "instamart",
	"instamart.in": "instamart",
	"blinkit.com":  "blinkit",
	"zeptonow.com": "zepto",
	"zepto.in":     "zepto",
	"amazon.in":    "amazon",
	"amazon.com":   "amazon",
	"amzn.in":      "amazon",
}

// platformFromURL infers the retail platform from a product URL's host. The
// host must be an allowed retail domain (or a direct subdomain of one); the
// URL is only a hint — it is never dereferenced, scraped, or opened.
func platformFromURL(u string) string {
	lu := strings.ToLower(strings.TrimSpace(u))
	if lu == "" {
		return ""
	}
	if !strings.Contains(lu, "://") && urlHostRe.MatchString(lu) {
		lu = "https://" + lu
	}
	parsed, err := url.Parse(lu)
	if err != nil {
		return ""
	}
	host := strings.TrimSuffix(strings.ToLower(parsed.Hostname()), ".")
	for allowed, platform := range allowedRetailHosts {
		if host == allowed || strings.HasSuffix(host, "."+allowed) {
			return platform
		}
	}
	return ""
}

// Identify resolves a Product from a URL and/or free text. Real-time title
// scraping of retailer pages is intentionally out of scope; URLs contribute
// only platform + slug hints, and the offline demo catalog supplies the
// canonical identity. The result always says so.
func (d *Deps) Identify(_ agent.Context, args IdentifyArgs) (IdentifyResult, error) {
	inputText := strings.TrimSpace(args.InputText)
	inputURL := strings.TrimSpace(args.InputURL)
	if inputText == "" && inputURL == "" {
		return IdentifyResult{}, fmt.Errorf("identify_product needs input_url and/or input_text")
	}

	platform := platformFromURL(inputURL)
	if inputText == "" && inputURL != "" {
		inputText = slugHint(inputURL)
	}

	entry, conf, ok := d.Catalog.FindProduct(inputText)
	if !ok {
		note := fmt.Sprintf("No match in the offline demo catalog for %q.", inputText)
		if platform != "" {
			note += fmt.Sprintf(" The URL looks like %s, but live page-title scraping is out of scope, so the product could not be resolved.", platform)
		}
		note += " Call get_offers with the raw text anyway — the live qbuys source may still find offers — but say plainly that the product itself was not identified."
		return IdentifyResult{Found: false, MatchConfidence: 0, Platform: platform, Note: note}, nil
	}

	product := entry.ToProduct(inputURL)
	note := "Product resolved against the offline demo catalog (deterministic, not live); URL page scraping is out of scope"
	if platform != "" {
		note += fmt.Sprintf("; inferred platform %q from the URL", platform)
	}
	note += "."
	return IdentifyResult{
		Found:           true,
		Product:         product,
		MatchConfidence: conf,
		Platform:        platform,
		Note:            note,
	}, nil
}

// slugHint extracts a human-ish string from the longest URL path segment
// (".../amul-taaza-milk-1-l/pr/xyz" -> "amul taaza milk 1 l").
func slugHint(rawURL string) string {
	lu := strings.TrimSpace(rawURL)
	if !strings.Contains(lu, "://") && urlHostRe.MatchString(lu) {
		lu = "https://" + lu
	}
	parsed, err := url.Parse(lu)
	if err != nil {
		return rawURL
	}
	best := ""
	for _, s := range strings.Split(strings.Trim(parsed.Path, "/"), "/") {
		s = strings.TrimSpace(s)
		if len(s) > len(best) && s != "pr" && s != "dp" && s != "p" && s != "item" {
			best = s
		}
	}
	best = strings.ReplaceAll(best, "-", " ")
	best = strings.ReplaceAll(best, "_", " ")
	if q := parsed.Query().Get("q"); best == "" && q != "" {
		best = q
	}
	return best
}

// ---- get_offers ----

// GetOffersArgs are the inputs of the get_offers tool.
type GetOffersArgs struct {
	ProductName string `json:"product_name"`
	PINCode     string `json:"pincode"`
	Brand       string `json:"brand,omitempty"`
	Quantity    string `json:"quantity,omitempty"`
}

// GetOffers fans out to the composite data source. Every offer is fully
// fee-computed in Go and labeled with its data source and timestamp; a
// retailer without usable data comes back as an explicit unavailable offer
// with a StatusReason — its numbers are never invented.
func (d *Deps) GetOffers(_ agent.Context, args GetOffersArgs) (retailers.SearchResult, error) {
	pincode := strings.TrimSpace(args.PINCode)
	if strings.TrimSpace(args.ProductName) == "" {
		return retailers.SearchResult{}, fmt.Errorf("get_offers needs a product_name")
	}
	if pincode == "" {
		return retailers.SearchResult{}, fmt.Errorf("get_offers needs a pincode")
	}

	now := d.now()
	q := retailers.SearchQuery{
		ProductName: strings.TrimSpace(args.ProductName),
		Brand:       strings.TrimSpace(args.Brand),
		Quantity:    strings.TrimSpace(args.Quantity),
		PINCode:     pincode,
	}
	offers, warnings := d.Composite.Offers(nil, q, now)
	return retailers.SearchResult{
		Query:       q.ProductName,
		PINCode:     pincode,
		Offers:      offers,
		Fulfillment: fulfillmentStatus(offers),
		Warnings:    warnings,
		FetchedAt:   now,
		Source:      summarizeSources(offers),
	}, nil
}

func fulfillmentStatus(offers []retailers.Offer) retailers.FulfillmentStatus {
	usable, total := 0, 0
	for _, o := range offers {
		if o.Retailer == retailers.RetailerUnknown {
			continue
		}
		total++
		if o.Status == retailers.StatusOK && o.InStock && o.Serviceable {
			usable++
		}
	}
	switch {
	case usable == 0:
		return retailers.FulfillmentFailed
	case usable < total:
		return retailers.FulfillmentPartial
	default:
		return retailers.FulfillmentOK
	}
}

func summarizeSources(offers []retailers.Offer) string {
	live, demo := 0, 0
	for _, o := range offers {
		switch o.Source {
		case retailers.SourceQBuysLive:
			live++
		case retailers.SourceDemo:
			demo++
		}
	}
	switch {
	case live > 0 && demo > 0:
		return fmt.Sprintf("mixed (%d live qbuys, %d offline demo)", live, demo)
	case live > 0:
		return retailers.SourceQBuysLive
	case demo > 0:
		return retailers.SourceDemo
	default:
		return "none"
	}
}

// ---- compare_offers ----

// CompareArgs are the inputs of the compare_offers tool: the offers exactly
// as returned by get_offers, plus any memberships the user mentioned.
type CompareArgs struct {
	ProductName string            `json:"product_name,omitempty"`
	PINCode     string            `json:"pincode"`
	Offers      []retailers.Offer `json:"offers"`
	Memberships []string          `json:"memberships,omitempty"` // e.g. ["amazon_prime", "instamart_one"]
}

// Compare deterministically ranks offers via retailers.Rank; all arithmetic
// is done in Go.
func (d *Deps) Compare(_ agent.Context, args CompareArgs) (retailers.Recommendation, error) {
	if len(args.Offers) == 0 {
		return retailers.Recommendation{}, fmt.Errorf("compare_offers needs at least one offer from get_offers")
	}
	memberships := retailers.MembershipsFor(args.Memberships)
	return retailers.Rank(args.Offers, memberships, strings.TrimSpace(args.PINCode), strings.TrimSpace(args.ProductName), d.now()), nil
}

// ---- check_serviceability ----

// ServiceabilityArgs are the inputs of the check_serviceability tool.
type ServiceabilityArgs struct {
	Retailer string `json:"retailer"`
	PINCode  string `json:"pincode"`
}

// Serviceability answers per-retailer pincode serviceability, blending the
// live qbuys fulfillment probe (quick-commerce only) with offline demo zone
// knowledge. Answers derived from the offline catalog are labeled estimates.
func (d *Deps) Serviceability(_ agent.Context, args ServiceabilityArgs) (retailers.ServiceabilityResult, error) {
	pincode := strings.TrimSpace(args.PINCode)
	if pincode == "" {
		return retailers.ServiceabilityResult{}, fmt.Errorf("check_serviceability needs a pincode")
	}
	r, err := retailers.ParseRetailer(args.Retailer)
	if err != nil {
		return retailers.ServiceabilityResult{}, err
	}
	var liveSrc retailers.DataSource
	if d.Live != nil {
		liveSrc = d.Live
	}
	hub := retailers.ServiceabilityHub{Live: liveSrc}
	return hub.Check(r, pincode, d.now()), nil
}

// ---- request_purchase_confirmation ----

// PurchaseConfirmationArgs are the inputs of the purchase approval gate. The
// tool is registered with RequireConfirmation: true, and the ADK framework
// asks the user to approve the call before this handler runs.
type PurchaseConfirmationArgs struct {
	Retailer    string `json:"retailer"`
	ProductName string `json:"product_name"`
	ProductURL  string `json:"product_url,omitempty"`
	FinalCost   int64  `json:"final_cost"` // paise
	Action      string `json:"action"`     // checkout | subscribe | pay
}

// PurchaseConfirmationResult reports the approval outcome.
type PurchaseConfirmationResult struct {
	Confirmed bool   `json:"confirmed"`
	Message   string `json:"message"`
}

// PurchaseConfirmation is the human-in-the-loop approval gate. The handler
// runs only after the user has approved the tool call through the ADK
// confirmation flow; on denial the ADK flow surfaces the rejection and the
// agent must report the action as cancelled. This handler performs no
// checkout itself — QuickCart Advisor never places orders — it only records
// that the gate was passed and hands the user the retailer's own link.
func (d *Deps) PurchaseConfirmation(_ agent.Context, args PurchaseConfirmationArgs) (PurchaseConfirmationResult, error) {
	switch strings.ToLower(strings.TrimSpace(args.Action)) {
	case "checkout", "subscribe", "pay":
	default:
		return PurchaseConfirmationResult{Confirmed: false, Message: fmt.Sprintf("unknown action %q; must be one of checkout, subscribe, pay", args.Action)}, nil
	}
	if strings.TrimSpace(args.Retailer) == "" || strings.TrimSpace(args.ProductName) == "" {
		return PurchaseConfirmationResult{Confirmed: false, Message: "retailer and product_name are required"}, nil
	}
	return PurchaseConfirmationResult{
		Confirmed: true,
		Message: fmt.Sprintf("User approved %s of %q on %s for %s. QuickCart Advisor does not execute the transaction — share the retailer's product/checkout link for the user to finish it in the app or site.",
			args.Action, args.ProductName, args.Retailer, retailers.FormatINR(args.FinalCost)),
	}, nil
}

// All builds the five ADK function tools in a stable order. A constructor
// failure aborts — a half-built tool set must never run.
func (d *Deps) All() ([]tool.Tool, error) {
	type spec struct {
		name  string
		desc  string
		build func(cfg functiontool.Config) (tool.Tool, error)
	}
	specs := []spec{
		{
			name: "identify_product",
			desc: "Resolve a product identity from a retailer product URL and/or free-text description. Uses the offline demo catalog plus URL platform/slug hints (live page scraping is out of scope). Returns the product, a match confidence in [0,1], and an honest note about how it was resolved.",
			build: func(cfg functiontool.Config) (tool.Tool, error) {
				return functiontool.New(cfg, d.Identify)
			},
		},
		{
			name: "get_offers",
			desc: "Fetch per-retailer offers for a product at an Indian PIN code across Swiggy Instamart, Blinkit, Zepto and Amazon India. Tries the live qbuys source for the three quick-commerce sites and falls back to the offline demo catalog on any failure (Amazon is always catalog-sourced). Every offer carries price, MRP, delivery/platform/handling/small-cart/other fees, taxes, discount, final delivered cost in paise, ETA minutes, stock and serviceability flags, a data-source label (qbuys-live or offline-demo-catalog) and an RFC3339 last-updated timestamp, plus product/checkout URLs. Retailers with no usable data return status unavailable or not_serviceable with a reason — data is never fabricated. All monetary amounts (price, fees, taxes, discount, final_delivered_cost) are in integer PAISE (₹1 = 100 paise); when presenting to the user divide by 100 and show ₹ with two decimals (e.g. 11749 paise = ₹117.49).",
			build: func(cfg functiontool.Config) (tool.Tool, error) {
				return functiontool.New(cfg, d.GetOffers)
			},
		},
		{
			name: "compare_offers",
			desc: "Deterministically rank the offers returned by get_offers: best = lowest final delivered cost among in-stock, serviceable offers (ties broken by faster ETA, then fewer fees). Also returns cheapest and fastest plus human-readable explanations (savings vs runner-up, speed trade-off, fee notes). Pass memberships such as [\"amazon_prime\", \"instamart_one\", \"blinkit_pass\", \"zepto_pass\"] when the user mentions any — Prime gives free delivery on eligible Amazon offers; the quick-commerce passes waive delivery fees on fast (<=20 min) or slow (>=45 min) deliveries. All arithmetic is done in Go. All monetary amounts (price, fees, taxes, discount, final_delivered_cost) are in integer PAISE (₹1 = 100 paise); when presenting to the user divide by 100 and show ₹ with two decimals (e.g. 11749 paise = ₹117.49).",
			build: func(cfg functiontool.Config) (tool.Tool, error) {
				return functiontool.New(cfg, d.Compare)
			},
		},
		{
			name: "check_serviceability",
			desc: "Check whether a retailer (instamart | blinkit | zepto | amazon) serves an Indian PIN code and get a delivery ETA estimate. Blends the live qbuys fulfillment probe where available with offline demo zone knowledge; every answer states whether it is live-confirmed or an estimate. Unknown pincodes come back not serviceable with a plain reason — never guessed as serviceable.",
			build: func(cfg functiontool.Config) (tool.Tool, error) {
				return functiontool.New(cfg, d.Serviceability)
			},
		},
		{
			name: "request_purchase_confirmation",
			desc: "MANDATORY human-in-the-loop approval gate before any checkout, subscription, or payment step. Call with retailer, product name, final cost in paise, and action (checkout | subscribe | pay). Present the checkout link as actionable ONLY after this tool returns approval. If the user denies it, state plainly that the action was cancelled. This tool never performs the purchase itself.",
			build: func(cfg functiontool.Config) (tool.Tool, error) {
				cfg.RequireConfirmation = true
				return functiontool.New(cfg, d.PurchaseConfirmation)
			},
		},
	}

	out := make([]tool.Tool, 0, len(specs))
	for _, s := range specs {
		t, err := buildNamedTool(s.name, s.desc, s.build)
		if err != nil {
			return nil, fmt.Errorf("build tool %q: %w", s.name, err)
		}
		out = append(out, t)
	}
	return out, nil
}

// buildNamedTool attaches each spec's name and description through the
// functiontool config so the LLM sees the tool docs; the confirmation flag
// stays in the spec closure (true only for request_purchase_confirmation).
func buildNamedTool(name, desc string, build func(cfg functiontool.Config) (tool.Tool, error)) (tool.Tool, error) {
	return build(functiontool.Config{Name: name, Description: desc})
}

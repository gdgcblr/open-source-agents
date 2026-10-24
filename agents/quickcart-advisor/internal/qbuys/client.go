// Package qbuys implements a best-effort HTTP client for the open-source
// qbuys ecosystem (https://github.com/vysakh0/qbserver,
// https://github.com/vysakh0/qbuys-server): public web APIs that aggregate
// Swiggy Instamart, Blinkit and Zepto catalog data.
//
// There is no official public API for these quick-commerce platforms, so this
// client treats the qbuys server as an untrusted, loosely-typed source: any
// error, timeout, or unexpected payload shape surfaces as an error that the
// caller converts into an explicitly "unavailable" offer with a reason. It
// never fabricates data. Amazon is not covered by qbuys at all.
package qbuys

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/retailers"
)

// DefaultBaseURL is where a local qbserver / qbuys-server usually runs; it is
// overridable via the QBUYS_BASE_URL environment variable.
const DefaultBaseURL = "http://localhost:8080"

// Timeout bounds any single live call.
const Timeout = 8 * time.Second

// platforms maps ADK-Go retailers to the qbuys "platform" query values.
var platforms = map[retailers.Retailer]string{
	retailers.RetailerInstamart: "instamart",
	retailers.RetailerBlinkit:   "blinkit",
	retailers.RetailerZepto:     "zepto",
}

// Client is a small, tolerant HTTP client for a qbuys-compatible server.
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

// NewClient builds a client. An empty baseURL falls back to DefaultBaseURL.
func NewClient(baseURL string) *Client {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = DefaultBaseURL
	}
	return &Client{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTP:    &http.Client{Timeout: Timeout},
	}
}

// platformKey returns the qbuys platform string for a retailer.
func platformKey(r retailers.Retailer) (string, bool) {
	p, ok := platforms[r]
	return p, ok
}

// Search performs a best-effort live search for one retailer and query at a
// pincode. It tries a small set of candidate qbuys/qbserver routes (the
// project has evolved them over time) and decodes the first usable response
// with a shape-tolerant decoder.
func (c *Client) Search(ctx context.Context, r retailers.Retailer, query, pincode string) ([]rawItem, error) {
	platform, ok := platformKey(r)
	if !ok {
		return nil, fmt.Errorf("qbuys does not cover retailer %s", r)
	}
	paths := []string{
		fmt.Sprintf("/api/search?platform=%s&q=%s&pincode=%s", url.QueryEscape(platform), url.QueryEscape(query), url.QueryEscape(pincode)),
		fmt.Sprintf("/api/search?platform=%s&query=%s&pincode=%s", url.QueryEscape(platform), url.QueryEscape(query), url.QueryEscape(pincode)),
		fmt.Sprintf("/search?platform=%s&q=%s&pincode=%s", url.QueryEscape(platform), url.QueryEscape(query), url.QueryEscape(pincode)),
		fmt.Sprintf("/api/products/search?platform=%s&q=%s&pincode=%s", url.QueryEscape(platform), url.QueryEscape(query), url.QueryEscape(pincode)),
	}
	var lastErr error
	for _, p := range paths {
		items, err := c.get(ctx, p)
		if err != nil {
			lastErr = err
			continue
		}
		return items, nil
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("no candidate search path produced data")
	}
	return nil, fmt.Errorf("qbuys %s search for %q at PIN %s failed: %w", platform, query, pincode, lastErr)
}

// get fetches one candidate path and tolerantly decodes whatever JSON comes
// back into raw items.
func (c *Client) get(ctx context.Context, path string) ([]rawItem, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+path, nil)
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "quickcart-advisor/1.0 (+https://github.com/seshachalam-yv/open-source-agents)")

	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, fmt.Errorf("GET %s: %w", path, err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET %s: HTTP %d", path, resp.StatusCode)
	}
	items, err := decodeItems(body)
	if err != nil {
		return nil, fmt.Errorf("decode %s: %w", path, err)
	}
	return items, nil
}

// decodeItems accepts several plausible JSON shapes from a qbuys-style
// server: a bare array, {items|data|results|products: [...]}. Every element
// is decoded into rawItem with entirely optional fields.
func decodeItems(body []byte) ([]rawItem, error) {
	body = []byte(strings.TrimSpace(string(body)))
	if len(body) == 0 {
		return nil, fmt.Errorf("empty response body")
	}
	var arr []json.RawMessage
	if body[0] == '[' {
		if err := json.Unmarshal(body, &arr); err != nil {
			return nil, fmt.Errorf("array decode: %w", err)
		}
	} else {
		var obj map[string]json.RawMessage
		if err := json.Unmarshal(body, &obj); err != nil {
			return nil, fmt.Errorf("object decode: %w", err)
		}
		found := false
		for _, key := range []string{"items", "data", "results", "products", "listings"} {
			if raw, ok := obj[key]; ok && len(raw) > 0 && raw[0] == '[' {
				if err := json.Unmarshal(raw, &arr); err != nil {
					return nil, fmt.Errorf("%q array decode: %w", key, err)
				}
				found = true
				break
			}
		}
		if !found {
			return nil, fmt.Errorf("no recognizable items array in response")
		}
	}
	items := make([]rawItem, 0, len(arr))
	for _, raw := range arr {
		var it rawItem
		if err := json.Unmarshal(raw, &it); err != nil {
			continue // drop undecodable rows rather than failing the whole call
		}
		items = append(items, it)
	}
	if len(items) == 0 {
		return nil, fmt.Errorf("response contained no usable items")
	}
	return items, nil
}

// rawItem is a shape-tolerant view of one loose qbuys JSON record. Every
// field is optional; number fields are decoded from number-or-string.
type rawItem struct {
	Name       string
	Brand      string
	Variant    string
	Quantity   string
	PricePaise int64
	MRPPaise   int64
	InStock    *bool
	ETA        int
	ProductURL string
}

// looseNumber decodes a JSON number, or a string containing one (qbuys
// payloads are loosely typed).
type looseNumber float64

func (n *looseNumber) UnmarshalJSON(b []byte) error {
	s := strings.Trim(string(b), `"`)
	if s == "" || s == "null" {
		*n = 0
		return nil
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return fmt.Errorf("loose number %q: %w", s, err)
	}
	*n = looseNumber(f)
	return nil
}

type looseString string

func (s *looseString) UnmarshalJSON(b []byte) error {
	t := strings.TrimSpace(string(b))
	if strings.HasPrefix(t, `"`) {
		var str string
		if err := json.Unmarshal(b, &str); err != nil {
			return err
		}
		*s = looseString(str)
		return nil
	}
	// numbers come through as their literal text
	*s = looseString(t)
	return nil
}

func (it *rawItem) UnmarshalJSON(b []byte) error {
	var m map[string]json.RawMessage
	if err := json.Unmarshal(b, &m); err != nil {
		return err
	}
	getString := func(keys ...string) string {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var s looseString
				if err := json.Unmarshal(raw, &s); err == nil && s != "" {
					return string(s)
				}
			}
		}
		return ""
	}
	getNum := func(keys ...string) looseNumber {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var n looseNumber
				if err := json.Unmarshal(raw, &n); err == nil {
					return n
				}
			}
		}
		return 0
	}
	getBool := func(keys ...string) *bool {
		for _, k := range keys {
			if raw, ok := m[k]; ok {
				var v bool
				if err := json.Unmarshal(raw, &v); err == nil {
					return &v
				}
				var s string
				if err := json.Unmarshal(raw, &s); err == nil {
					v := strings.EqualFold(s, "true") || s == "1" || strings.EqualFold(s, "yes")
					return &v
				}
			}
		}
		return nil
	}

	it.Name = getString("name", "product_name", "productName", "title")
	it.Brand = getString("brand", "brand_name", "brandName")
	it.Variant = getString("variant", "variation")
	it.Quantity = getString("quantity", "unit", "pack_size", "packSize", "weight")
	it.ProductURL = getString("product_url", "productUrl", "url", "link", "deeplink", "deep_link")

	// Money: qbuys-style servers variously report rupees or paise. We accept
	// paise fields directly, and treat decimal-looking rupee fields
	// (price, mrp) as rupees when they contain a fraction, and as rupees
	// when small (< 50_000) — Indian qcomm items rarely exceed ₹500. A value
	// explicitly named *_paise or *_in_paise is always paise.
	pricePaise := getNum("price_paise", "priceInPaise", "price_in_paise", "selling_price_paise")
	mrpPaise := getNum("mrp_paise", "mrpInPaise", "mrp_in_paise")
	if pricePaise == 0 {
		rupees := getNum("price", "selling_price", "sellingPrice", "offer_price", "offerPrice", "discounted_price")
		pricePaise = rupeesToPaise(float64(rupees))
	}
	if mrpPaise == 0 {
		rupees := getNum("mrp", "list_price", "listPrice", "original_price", "originalPrice")
		mrpPaise = rupeesToPaise(float64(rupees))
	}
	it.PricePaise = int64(pricePaise)
	it.MRPPaise = int64(mrpPaise)
	it.InStock = getBool("in_stock", "inStock", "available", "is_available", "isAvailable")
	it.ETA = int(getNum("eta_minutes", "etaMinutes", "eta", "delivery_time", "deliveryTime", "delivery_time_mins"))
	return nil
}

// rupeesToPaise converts a loose rupee figure to paise. Values that already
// look like paise (large integers) pass through untouched.
func rupeesToPaise(v float64) looseNumber {
	if v == 0 {
		return 0
	}
	if v == float64(int64(v)) && v >= 50000 {
		// ≥ ₹500 as an integer is far more likely to already be paise.
		return looseNumber(v)
	}
	return looseNumber(v * 100)
}

// bestItem picks the raw item that most plausibly matches the query: it
// prefers name containment of the query's significant tokens.
func bestItem(items []rawItem, query string) rawItem {
	tokens := strings.Fields(strings.ToLower(query))
	score := func(it rawItem) int {
		name := strings.ToLower(it.Name + " " + it.Brand)
		s := 0
		for _, t := range tokens {
			if len(t) > 2 && strings.Contains(name, t) {
				s++
			}
		}
		return s
	}
	best := items[0]
	bestScore := -1
	for _, it := range items {
		if s := score(it); s > bestScore {
			best, bestScore = it, s
		}
	}
	return best
}

// Package retailers contains the domain model for the QuickCart Advisor
// agent: products, per-retailer offers, fee arithmetic, membership benefits
// and deterministic ranking. It has no dependency on the ADK, any LLM, or
// the network, so all of it is unit-testable in isolation.
package retailers

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// Data-source labels recorded on every Offer.Source and Product.Source so
// the agent (and the user) can always tell live data from demo data.
const (
	SourceQBuysLive = "qbuys-live"
	SourceDemo      = "offline-demo-catalog"
)

// Offer Status values. Anything other than StatusOK is unusable for ranking.
const (
	StatusOK             = "ok"
	StatusUnavailable    = "unavailable"
	StatusNotServiceable = "not_serviceable"
	StatusOutOfStock     = "out_of_stock"
)

// Well-known membership IDs accepted by Rank (compare_offers). Matching is
// case-insensitive.
const (
	MembershipAmazonPrime  = "amazon_prime"
	MembershipInstamartOne = "instamart_one"
	MembershipBlinkitPass  = "blinkit_pass"
	MembershipZeptoPass    = "zepto_pass"
)

// minutesPerDay is used to express multi-day delivery ETAs in minutes.
const minutesPerDay = 24 * 60

// Delivery-speed thresholds, in minutes: offers at or under fastETA and at
// or above slowETA are membership-fee-exempt on their retailer.
const (
	fastETA = 20
	slowETA = 45
)

// Retailer identifies one of the four supported stores.
type Retailer int

const (
	RetailerUnknown Retailer = iota
	RetailerInstamart
	RetailerBlinkit
	RetailerZepto
	RetailerAmazon
)

// AllRetailers lists the four supported retailers in a stable order.
var AllRetailers = []Retailer{RetailerInstamart, RetailerBlinkit, RetailerZepto, RetailerAmazon}

var retailerNames = map[Retailer]string{
	RetailerInstamart: "instamart",
	RetailerBlinkit:   "blinkit",
	RetailerZepto:     "zepto",
	RetailerAmazon:    "amazon",
}

// String returns the canonical lowercase name ("instamart", ...).
func (r Retailer) String() string {
	if s, ok := retailerNames[r]; ok {
		return s
	}
	return "unknown"
}

// DisplayName returns a human-friendly retailer name.
func (r Retailer) DisplayName() string {
	switch r {
	case RetailerInstamart:
		return "Swiggy Instamart"
	case RetailerBlinkit:
		return "Blinkit"
	case RetailerZepto:
		return "Zepto"
	case RetailerAmazon:
		return "Amazon India"
	default:
		return "Unknown retailer"
	}
}

// ParseRetailer converts a (case-insensitive) name or common alias into a
// Retailer. It returns an error for unrecognized values.
func ParseRetailer(s string) (Retailer, error) {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "instamart", "swiggy", "swiggy instamart", "swiggy_instamart":
		return RetailerInstamart, nil
	case "blinkit", "grofers", "blinkit (zomato)":
		return RetailerBlinkit, nil
	case "zepto":
		return RetailerZepto, nil
	case "amazon", "amazon india", "amazon.in", "amazon_india", "amazon fresh":
		return RetailerAmazon, nil
	default:
		return RetailerUnknown, fmt.Errorf("unknown retailer %q", s)
	}
}

// MarshalJSON / UnmarshalJSON keep the JSON wire form a plain string so the
// LLM and tool schemas see readable values.
func (r Retailer) MarshalJSON() ([]byte, error) {
	return []byte(fmt.Sprintf("%q", r.String())), nil
}

// UnmarshalJSON implements json.Unmarshaler. It accepts both the canonical
// string names ("instamart", ...) and the integer ordinals (1=instamart,
// 2=blinkit, 3=zepto, 4=amazon), because the ADK/jsonschema generator
// renders the int-kind Retailer type as an INTEGER enum, so schema-valid
// LLM payloads may carry either form — quoted ("2") or bare (2).
func (r *Retailer) UnmarshalJSON(b []byte) error {
	s := strings.Trim(string(b), `"`)
	if s == "" {
		*r = RetailerUnknown
		return nil
	}
	if n, err := strconv.Atoi(s); err == nil {
		ordinal := Retailer(n)
		if _, ok := retailerNames[ordinal]; ok {
			*r = ordinal
			return nil
		}
		return fmt.Errorf("unknown retailer ordinal %d", n)
	}
	parsed, err := ParseRetailer(s)
	if err != nil {
		return err
	}
	*r = parsed
	return nil
}

// Delivery tier of an offer, derived from its ETA. Memberships only remove
// delivery fees on Fast or Slow deliveries — mid-range "standard" deliveries
// are excluded, mirroring how quick-commerce passes typically apply to
// specific speed tiers.
type DeliveryTier int

const (
	TierFast DeliveryTier = iota + 1
	TierStandard
	TierSlow
	TierUnknown
)

// String returns "fast", "standard", "slow" or "" for unknown.
func (t DeliveryTier) String() string {
	switch t {
	case TierFast:
		return "fast"
	case TierStandard:
		return "standard"
	case TierSlow:
		return "slow"
	default:
		return ""
	}
}

// Product is a normalized product identity resolved from a URL or free text.
type Product struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	Brand        string `json:"brand"`
	Variant      string `json:"variant,omitempty"`
	Quantity     string `json:"quantity,omitempty"`
	Category     string `json:"category,omitempty"`
	SourceURL    string `json:"source_url,omitempty"`
	CanonicalKey string `json:"canonical_key,omitempty"`
	// Source records where this identification came from (always the demo
	// catalog today — live URL title scraping is intentionally out of scope).
	Source string `json:"source,omitempty"`
}

// FeeBreakdown is the per-fee detail of an offer, for transparent reporting.
// Every amount is in integer paise (₹1 = 100 paise).
type FeeBreakdown struct {
	DeliveryFee  int64 `json:"delivery_fee"`
	PlatformFee  int64 `json:"platform_fee"`
	HandlingFee  int64 `json:"handling_fee,omitempty"`
	SmallCartFee int64 `json:"small_cart_fee,omitempty"`
	OtherFees    int64 `json:"other_fees,omitempty"`
}

// Total returns the sum of all fee components in paise.
func (f FeeBreakdown) Total() int64 {
	return f.DeliveryFee + f.PlatformFee + f.HandlingFee + f.SmallCartFee + f.OtherFees
}

// Offer is one retailer's offer for one product (mirrors the qbuys model of
// a catalog item plus fulfillment options). All money amounts are in
// integer paise (₹1 = 100 paise).
type Offer struct {
	Retailer    Retailer `json:"retailer"`
	ProductName string   `json:"product_name"`
	Brand       string   `json:"brand,omitempty"`
	Variant     string   `json:"variant,omitempty"`
	Quantity    string   `json:"quantity,omitempty"`

	Price        int64 `json:"price"`        // selling price, paise
	MRP          int64 `json:"mrp"`          // maximum retail price, paise
	DeliveryFee  int64 `json:"delivery_fee"` // paid delivery fee, paise (0 when free)
	PlatformFee  int64 `json:"platform_fee"` // paise
	HandlingFee  int64 `json:"handling_fee,omitempty"`
	SmallCartFee int64 `json:"small_cart_fee,omitempty"`
	OtherFees    int64 `json:"other_fees,omitempty"`
	Taxes        int64 `json:"taxes,omitempty"`
	Discount     int64 `json:"discount,omitempty"` // reductions off MRP, paise

	// MembershipBenefits is a human-readable description of which membership
	// benefit (if any) already shaped this offer's fees, e.g. "Amazon Prime:
	// free delivery".
	MembershipBenefits string `json:"membership_benefits,omitempty"`

	// FinalDeliveredCost is the total amount payable for door delivery:
	// Price − Discount + all fees + Taxes. Computed exclusively in Go by
	// ComputeFees, never by the LLM.
	FinalDeliveredCost int64 `json:"final_delivered_cost"`

	InStock     bool `json:"in_stock"`
	Serviceable bool `json:"serviceable"`
	ETAMinutes  int  `json:"eta_minutes"` // 0 when unknown/not serviceable

	// Source labels where this data came from: SourceQBuysLive or
	// SourceDemo. Never presented as anything else.
	Source      string    `json:"source"`
	LastUpdated time.Time `json:"last_updated"` // RFC3339 on the wire

	ProductURL  string `json:"product_url,omitempty"`
	CheckoutURL string `json:"checkout_url,omitempty"`

	// Status is StatusOK only when the offer is fully usable for ranking.
	// Unavailable/out-of-stock reasons go in StatusReason; nothing is ever
	// silently guessed.
	Status       string `json:"status"`
	StatusReason string `json:"status_reason,omitempty"`
}

// SavingsPerUnit returns MRP − Price clamped at ≥ 0 (the headline saving on
// the product itself, before fees).
func (o Offer) SavingsPerUnit() int64 {
	if s := o.MRP - o.Price; s > 0 {
		return s
	}
	return 0
}

// Fees returns the fee components as a FeeBreakdown.
func (o Offer) Fees() FeeBreakdown {
	return FeeBreakdown{
		DeliveryFee:  o.DeliveryFee,
		PlatformFee:  o.PlatformFee,
		HandlingFee:  o.HandlingFee,
		SmallCartFee: o.SmallCartFee,
		OtherFees:    o.OtherFees,
	}
}

// Tier derives the delivery tier from ETAMinutes.
func (o Offer) Tier() DeliveryTier {
	switch {
	case o.ETAMinutes <= 0:
		return TierUnknown
	case o.ETAMinutes <= fastETA:
		return TierFast
	case o.ETAMinutes >= slowETA:
		return TierSlow
	default:
		return TierStandard
	}
}

// SearchResult is the outcome of a per-pincode product lookup.
type SearchResult struct {
	Query   string `json:"query"`
	PINCode string `json:"pincode"`

	Offers []Offer `json:"offers"`

	// Fulfillment mirrors the qbuys model: catalog items can exist while all
	// fulfillment options failed for a pincode.
	Fulfillment FulfillmentStatus `json:"fulfillment"`

	// Warnings carry honest caveats (e.g. "qbuys live source unreachable,
	// used offline demo data for Instamart").
	Warnings []string `json:"warnings,omitempty"`

	// FetchedAt / Source summarize provenance for the result as a whole.
	FetchedAt time.Time `json:"fetched_at"`
	Source    string    `json:"source"`
}

// FulfillmentStatus flags whether any fulfillment path succeeded.
type FulfillmentStatus string

const (
	FulfillmentOK      FulfillmentStatus = "fulfillment_ok"
	FulfillmentPartial FulfillmentStatus = "fulfillment_partial" // some retailers failed
	FulfillmentFailed  FulfillmentStatus = "fulfillment_failed"  // no retailer responded
)

// FulfillmentResult is the per-retailer outcome of TryFulfill for a pincode:
// either an offer or an explicit failure with a reason.
type FulfillmentResult struct {
	Retailer  Retailer  `json:"retailer"`
	Offer     *Offer    `json:"offer,omitempty"`
	Reason    string    `json:"reason,omitempty"` // populated when Offer is nil/unusable
	CheckedAt time.Time `json:"checked_at"`
}

// Recommendation is the deterministic comparison outcome produced by Rank.
type Recommendation struct {
	Best     Offer `json:"best"`
	Cheapest Offer `json:"cheapest"`
	Fastest  Offer `json:"fastest"`

	// RankedOffers holds every usable offer, best first.
	RankedOffers []Offer `json:"ranked_offers"`

	// Excluded holds offers excluded from ranking (unavailable, out of
	// stock, or not serviceable), with their reasons intact.
	Excluded []Offer `json:"excluded,omitempty"`

	HasUsable bool `json:"has_usable"` // false when no offer could be ranked

	// Explanations contains one human-readable line per decision (savings
	// vs runner-up, delivery-speed trade-off, fee note, ...).
	Explanations []string `json:"explanations"`

	ComparedAt time.Time `json:"compared_at"`
	PINCode    string    `json:"pincode,omitempty"`
	Query      string    `json:"query,omitempty"`
}

// ServiceabilityResult is the per-retailer, per-pincode answer of
// check_serviceability. Any answer may be an estimate — that is stated in
// Reason/Source and never hidden.
type ServiceabilityResult struct {
	Retailer    Retailer  `json:"retailer"`
	PINCode     string    `json:"pincode"`
	Serviceable bool      `json:"serviceable"`
	ETAMinutes  int       `json:"eta_minutes,omitempty"`
	Reason      string    `json:"reason"`
	IsEstimate  bool      `json:"is_estimate"`
	Source      string    `json:"source"` // SourceQBuysLive / SourceDemo
	CheckedAt   time.Time `json:"checked_at"`
}

// Membership describes a user's subscription that can reduce fees.
type Membership struct {
	ID       string   `json:"id"` // e.g. MembershipAmazonPrime
	Retailer Retailer `json:"retailer"`
}

// MembershipsFor builds the Membership set for the well-known membership ID
// list a user mentions (["amazon_prime", "instamart_one", ...]).
// Unrecognized IDs are ignored.
func MembershipsFor(ids []string) []Membership {
	var out []Membership
	for _, id := range ids {
		switch strings.ToLower(strings.TrimSpace(id)) {
		case MembershipAmazonPrime:
			out = append(out, Membership{ID: MembershipAmazonPrime, Retailer: RetailerAmazon})
		case MembershipInstamartOne:
			out = append(out, Membership{ID: MembershipInstamartOne, Retailer: RetailerInstamart})
		case MembershipBlinkitPass:
			out = append(out, Membership{ID: MembershipBlinkitPass, Retailer: RetailerBlinkit})
		case MembershipZeptoPass:
			out = append(out, Membership{ID: MembershipZeptoPass, Retailer: RetailerZepto})
		}
	}
	return out
}

var membershipLabels = map[string]string{
	MembershipAmazonPrime:  "Amazon Prime",
	MembershipInstamartOne: "Swiggy One (Instamart)",
	MembershipBlinkitPass:  "Blinkit Pass",
	MembershipZeptoPass:    "Zepto Pass",
}

// MembershipLabel returns the display label for a membership ID.
func MembershipLabel(id string) string {
	if l, ok := membershipLabels[strings.ToLower(strings.TrimSpace(id))]; ok {
		return l
	}
	return id
}

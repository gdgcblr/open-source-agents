package retailers

import (
	"context"
	"fmt"
	"sort"
	"time"
)

// DataSource is a best-effort source of retailer data for a product at a
// pincode. Implementations must never fabricate data: on any failure they
// return an error and the caller converts it into an explicit unavailable
// Offer with a StatusReason, or falls back to another source.
type DataSource interface {
	// Name identifies the source ("qbuys-live", "offline-demo-catalog", ...).
	Name() string
	// Retailers lists the retailers this source can serve.
	Retailers() []Retailer
	// Lookup returns raw (not yet fee-computed) offers for the query at the
	// pincode. Offers for retailers with no data may be returned with
	// Serviceable=false and a StatusReason instead of being omitted.
	Lookup(ctx context.Context, query SearchQuery) ([]Offer, error)
	// TryFulfill, for sources that support it, returns per-retailer
	// fulfillment outcomes for a pincode. Sources without fulfillment
	// probing return nil, nil.
	TryFulfill(pincode string, now time.Time) map[Retailer]FulfillmentResult
}

// SearchQuery is a normalized product lookup.
type SearchQuery struct {
	ProductName string
	Brand       string
	Quantity    string
	PINCode     string
}

// Composite tries its sources in order, merging live offers per retailer
// with catalog fallbacks. It never hides a failure: every retailer targeted
// by the query ends up either with a usable Offer or with an explicit
// unavailable Offer whose StatusReason says why.
type Composite struct {
	// Live is a best-effort live source (qbuys). May be nil.
	Live DataSource
	// Catalog is the always-available offline demo catalog.
	Catalog DataSource
}

// NewComposite builds the standard source stack: qbuys live for the three
// quick-commerce retailers, offline demo catalog as the base for all four.
func NewComposite(live, catalog DataSource) *Composite {
	return &Composite{Live: live, Catalog: catalog}
}

// Offers returns one offer per supported retailer for the query, labeled by
// source, plus warnings describing any fallback that happened.
func (c *Composite) Offers(ctx context.Context, q SearchQuery, now time.Time) ([]Offer, []string) {
	warnings := []string{}
	demoOffers := map[Retailer]Offer{}
	if c.Catalog != nil {
		if offers, err := c.Catalog.Lookup(ctx, q); err == nil {
			for _, o := range offers {
				demoOffers[o.Retailer] = o
			}
		} else {
			warnings = append(warnings, fmt.Sprintf("offline catalog lookup failed: %v", err))
		}
	}

	liveOffers := map[Retailer]Offer{}
	liveOK := false
	if c.Live != nil && q.PINCode != "" {
		offers, err := c.Live.Lookup(ctx, q)
		if err != nil {
			warnings = append(warnings, fmt.Sprintf("live qbuys source unavailable (%v); used offline demo catalog data for affected retailers", err))
		} else {
			liveOK = true
			for _, o := range offers {
				liveOffers[o.Retailer] = o
			}
		}
	}

	coverage := map[Retailer]bool{}
	if c.Live != nil {
		for _, r := range c.Live.Retailers() {
			coverage[r] = true
		}
	}

	merged := make([]Offer, 0, len(AllRetailers))
	for _, r := range AllRetailers {
		live, hasLive := liveOffers[r]
		demo, hasDemo := demoOffers[r]

		switch {
		case hasLive:
			merged = append(merged, ComputeFees(live))
		case coverage[r] && c.Live != nil && liveOK:
			// The live source responded but had no data for this retailer;
			// prefer live truth ("not found") over demo data? No — demo data
			// is explicitly labeled, so surface it and warn. But if the demo
			// catalog also has nothing, emit an explicit unavailable offer.
			if hasDemo {
				warnings = append(warnings, fmt.Sprintf("no live qbuys data for %s at PIN %s; showing offline demo catalog offer instead", r.DisplayName(), q.PINCode))
				merged = append(merged, ComputeFees(demo))
			} else {
				merged = append(merged, unavailableOffer(r, q, now, fmt.Sprintf("live qbuys source had no %s data for %q at PIN %s", r.DisplayName(), q.ProductName, q.PINCode)))
			}
		case hasDemo:
			merged = append(merged, ComputeFees(demo))
		default:
			merged = append(merged, unavailableOffer(r, q, now, fmt.Sprintf("no data source has %s offers for %q at PIN %s", r.DisplayName(), q.ProductName, q.PINCode)))
		}
	}
	return merged, warnings
}

// TryFulfill fans the pincode fulfillment probe out to the live source if it
// supports it; per-retailer catalog serviceability fills any gap.
func (c *Composite) TryFulfill(pincode string, now time.Time) map[Retailer]FulfillmentResult {
	out := make(map[Retailer]FulfillmentResult, len(AllRetailers))
	if c.Live != nil {
		for r, res := range c.Live.TryFulfill(pincode, now) {
			out[r] = res
		}
	}
	hub := ServiceabilityHub{Live: c.Live}
	for _, r := range AllRetailers {
		if _, ok := out[r]; ok {
			continue
		}
		svc := hub.Check(r, pincode, now)
		out[r] = FulfillmentResult{Retailer: r, Reason: svc.Reason, CheckedAt: svc.CheckedAt}
	}
	return out
}

// unavailableOffer builds an explicit "we have no data" offer — never a
// fabricated price.
func unavailableOffer(r Retailer, q SearchQuery, now time.Time, reason string) Offer {
	return Offer{
		Retailer:     r,
		ProductName:  q.ProductName,
		Brand:        q.Brand,
		Quantity:     q.Quantity,
		Serviceable:  false,
		Status:       StatusUnavailable,
		StatusReason: reason,
		Source:       "none",
		LastUpdated:  now.UTC(),
	}
}

// SortByCost orders offers by FinalDeliveredCost ascending (usable first) —
// a helper for deterministic display ordering outside Rank.
func SortByCost(offers []Offer) {
	sort.SliceStable(offers, func(i, j int) bool {
		ui, uj := usableOffer(offers[i]), usableOffer(offers[j])
		if ui != uj {
			return ui
		}
		return compareOffers(offers[i], offers[j]) < 0
	})
}

package qbuys

import (
	"context"
	"fmt"
	"time"

	"github.com/seshachalam-yv/open-source-agents/agents/quickcart-advisor/internal/retailers"
)

// Source adapts the qbuys Client to the retailers.DataSource interface. It is
// deliberately best-effort: every failure becomes an error, which the
// Composite converts into warnings plus an offline-catalog fallback — never
// into fabricated prices.
type Source struct {
	Client *Client
	Now    func() time.Time // tests can pin time; nil means time.Now
}

var _ retailers.DataSource = (*Source)(nil)

// NewSource builds a Source over a client (a nil client gets the default).
func NewSource(c *Client) *Source {
	if c == nil {
		c = NewClient("")
	}
	return &Source{Client: c}
}

// Name implements DataSource; the label flows into Offer.Source.
func (s *Source) Name() string { return retailers.SourceQBuysLive }

// Retailers implements DataSource: qbuys covers only the three
// quick-commerce platforms — never Amazon.
func (s *Source) Retailers() []retailers.Retailer {
	return []retailers.Retailer{retailers.RetailerInstamart, retailers.RetailerBlinkit, retailers.RetailerZepto}
}

func (s *Source) now() time.Time {
	if s.Now != nil {
		return s.Now().UTC()
	}
	return time.Now().UTC()
}

// Lookup implements DataSource. It queries the live server once per covered
// retailer and converts the best-matching raw item into a raw Offer. A
// retailer that errors yields an explicit unavailable Offer carrying the
// reason — the caller still sees a full four-retailer shape.
func (s *Source) Lookup(ctx context.Context, q retailers.SearchQuery) ([]retailers.Offer, error) {
	now := s.now()
	if q.PINCode == "" {
		return nil, fmt.Errorf("qbuys live lookups require a pincode")
	}
	offers := make([]retailers.Offer, 0, 3)
	var firstErr error
	for _, r := range s.Retailers() {
		items, err := s.Client.Search(ctx, r, q.ProductName, q.PINCode)
		if err != nil {
			if firstErr == nil {
				firstErr = err
			}
			offers = append(offers, retailers.Offer{
				Retailer:     r,
				ProductName:  q.ProductName,
				Brand:        q.Brand,
				Quantity:     q.Quantity,
				Serviceable:  false,
				Status:       retailers.StatusUnavailable,
				StatusReason: fmt.Sprintf("live qbuys lookup failed: %v", err),
				Source:       retailers.SourceQBuysLive,
				LastUpdated:  now,
			})
			continue
		}
		offers = append(offers, s.itemToOffer(bestItem(items, q.ProductName), r, q, now))
	}
	if firstErr != nil && allUnavailable(offers) {
		return offers, fmt.Errorf("qbuys live source unreachable for all quick-commerce retailers: %w", firstErr)
	}
	return offers, nil
}

func allUnavailable(offers []retailers.Offer) bool {
	for _, o := range offers {
		if o.Status == retailers.StatusOK {
			return false
		}
	}
	return true
}

// itemToOffer converts a raw qbuys item into a raw Offer. Fields the live
// payload does not carry keep zero values and, where meaningful, a
// StatusReason note — nothing is invented.
func (s *Source) itemToOffer(it rawItem, r retailers.Retailer, q retailers.SearchQuery, now time.Time) retailers.Offer {
	name := it.Name
	if name == "" {
		name = q.ProductName
	}
	o := retailers.Offer{
		Retailer:     r,
		ProductName:  name,
		Brand:        it.Brand,
		Variant:      it.Variant,
		Quantity:     it.Quantity,
		Price:        it.PricePaise,
		MRP:          it.MRPPaise,
		InStock:      it.InStock == nil || *it.InStock, // unknown stock is treated as in-stock but flagged below
		Serviceable:  true,
		ETAMinutes:   it.ETA,
		Source:       retailers.SourceQBuysLive,
		LastUpdated:  now,
		ProductURL:   it.ProductURL,
		CheckoutURL:  it.ProductURL,
		Status:       retailers.StatusOK,
		StatusReason: liveFieldNotes(it),
	}
	if o.MRP == 0 {
		o.MRP = o.Price
	}
	if o.Price <= 0 {
		o.Serviceable = false
		o.Status = retailers.StatusUnavailable
		o.StatusReason = appendNote(o.StatusReason, "live qbuys payload carried no usable price")
	}
	if it.InStock == nil {
		o.StatusReason = appendNote(o.StatusReason, "live qbuys payload did not state stock status; assuming in stock")
	}
	if o.ETAMinutes <= 0 {
		o.ETAMinutes = 0
		o.StatusReason = appendNote(o.StatusReason, "live qbuys payload carried no ETA")
	}
	return o
}

func liveFieldNotes(it rawItem) string {
	return ""
}

func appendNote(existing, note string) string {
	if existing == "" {
		return note
	}
	return existing + "; " + note
}

// TryFulfill implements DataSource with a lightweight probe: a one-word
// availability search per retailer. A usable answer means the platform
// serves the pincode; anything else is an explicit failure with a reason.
// This mirrors the qbuys FulfillmentResult model: failures are reported, not
// hidden.
func (s *Source) TryFulfill(pincode string, now time.Time) map[retailers.Retailer]retailers.FulfillmentResult {
	out := make(map[retailers.Retailer]retailers.FulfillmentResult, 3)
	ctx, cancel := context.WithTimeout(context.Background(), Timeout)
	defer cancel()
	for _, r := range s.Retailers() {
		res := retailers.FulfillmentResult{Retailer: r, CheckedAt: now.UTC()}
		_, err := s.Client.Search(ctx, r, "milk", pincode)
		if err != nil {
			res.Reason = fmt.Sprintf("qbuys fulfillment probe failed: %v", err)
		}
		out[r] = res
	}
	return out
}

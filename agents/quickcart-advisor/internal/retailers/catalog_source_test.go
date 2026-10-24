package retailers

import (
	"context"
	"errors"
	"testing"
	"time"
)

// equalOffer ignores LastUpdated (set at call time) and compares the rest.
func equalOffer(a, b Offer) bool {
	a.LastUpdated = time.Time{}
	b.LastUpdated = time.Time{}
	return a == b
}

func TestCatalogLookupDeterministic(t *testing.T) {
	src := CatalogSource{}
	q := SearchQuery{ProductName: "Amul Taaza Milk 1L", PINCode: "560001"}

	first, err := src.Lookup(context.Background(), q)
	if err != nil {
		t.Fatalf("first Lookup: %v", err)
	}
	second, err := src.Lookup(context.Background(), q)
	if err != nil {
		t.Fatalf("second Lookup: %v", err)
	}
	if len(first) != len(second) {
		t.Fatalf("offer count differs: %d vs %d", len(first), len(second))
	}
	if len(first) != len(AllRetailers) {
		t.Fatalf("want %d offers, got %d", len(AllRetailers), len(first))
	}
	for i := range first {
		if !equalOffer(first[i], second[i]) {
			t.Errorf("offer %d not deterministic:\nfirst:  %+v\nsecond: %+v", i, first[i], second[i])
		}
	}
}

func TestCatalogSourceCoversAllFourRetailers(t *testing.T) {
	src := CatalogSource{}
	got := map[Retailer]bool{}
	for _, r := range src.Retailers() {
		got[r] = true
	}
	for _, want := range []Retailer{RetailerInstamart, RetailerBlinkit, RetailerZepto, RetailerAmazon} {
		if !got[want] {
			t.Errorf("Retailers() missing %s", want)
		}
	}

	offers, err := src.Lookup(context.Background(), SearchQuery{ProductName: "Amul Taaza Milk 1L", PINCode: "560001"})
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	seen := map[Retailer]bool{}
	for _, o := range offers {
		seen[o.Retailer] = true
		if o.Source != SourceDemo {
			t.Errorf("offer for %s has Source %q, want %q", o.Retailer, o.Source, SourceDemo)
		}
	}
	if !seen[RetailerAmazon] {
		t.Error("no offer for amazon")
	}
	for _, r := range AllRetailers {
		if !seen[r] {
			t.Errorf("no offer for %s", r)
		}
	}
}

func TestMembershipsFor(t *testing.T) {
	ms := MembershipsFor([]string{"amazon_prime", "zepto_pass"})
	if len(ms) != 2 {
		t.Fatalf("want 2 memberships, got %d: %+v", len(ms), ms)
	}
	if ms[0].ID != MembershipAmazonPrime || ms[0].Retailer != RetailerAmazon {
		t.Errorf("unexpected membership %+v", ms[0])
	}
	if ms[1].ID != MembershipZeptoPass || ms[1].Retailer != RetailerZepto {
		t.Errorf("unexpected membership %+v", ms[1])
	}

	// Unknown IDs are ignored; whitespace/case tolerated for known ones.
	ms = MembershipsFor([]string{"bogus_membership", " Amazon_Prime ", "nope"})
	if len(ms) != 1 {
		t.Fatalf("want 1 membership after ignoring unknowns, got %d: %+v", len(ms), ms)
	}
	if ms[0].ID != MembershipAmazonPrime {
		t.Errorf("got ID %q, want %q", ms[0].ID, MembershipAmazonPrime)
	}

	if ms := MembershipsFor(nil); len(ms) != 0 {
		t.Errorf("nil input: want 0 memberships, got %d", len(ms))
	}
}

func TestCompositeNilLiveUsesCatalog(t *testing.T) {
	c := NewComposite(nil, CatalogSource{})
	offers, warnings := c.Offers(context.Background(), SearchQuery{ProductName: "Amul Taaza Milk 1L", PINCode: "560001"}, time.Now())
	if len(warnings) != 0 {
		t.Errorf("unexpected warnings: %v", warnings)
	}
	if len(offers) != len(AllRetailers) {
		t.Fatalf("want %d offers (one per retailer), got %d", len(AllRetailers), len(offers))
	}
	for _, o := range offers {
		if o.Source == "" {
			t.Errorf("offer for %s has empty Source label", o.Retailer)
		}
		if o.Source != SourceDemo {
			t.Errorf("offer for %s has Source %q, want %q", o.Retailer, o.Source, SourceDemo)
		}
	}
}

// stubLiveSource always fails, simulating an unreachable live backend.
type stubLiveSource struct{}

func (stubLiveSource) Name() string { return SourceQBuysLive }
func (stubLiveSource) Retailers() []Retailer {
	return []Retailer{RetailerInstamart, RetailerBlinkit, RetailerZepto}
}
func (stubLiveSource) Lookup(context.Context, SearchQuery) ([]Offer, error) {
	return nil, errors.New("connection refused (stub)")
}
func (stubLiveSource) TryFulfill(string, time.Time) map[Retailer]FulfillmentResult { return nil }

func TestCompositeUnreachableLiveFallsBackToCatalog(t *testing.T) {
	c := NewComposite(stubLiveSource{}, CatalogSource{})
	offers, warnings := c.Offers(context.Background(), SearchQuery{ProductName: "Amul Taaza Milk 1L", PINCode: "560001"}, time.Now())
	if len(offers) != len(AllRetailers) {
		t.Fatalf("want %d offers via catalog fallback, got %d", len(AllRetailers), len(offers))
	}
	if len(warnings) == 0 {
		t.Error("expected a fallback warning mentioning the unreachable live source")
	}
	for _, o := range offers {
		if o.Source == "" {
			t.Errorf("offer for %s has empty Source label", o.Retailer)
		}
		if o.Source != SourceDemo {
			t.Errorf("offer for %s has Source %q, want %q (catalog fallback)", o.Retailer, o.Source, SourceDemo)
		}
	}
}

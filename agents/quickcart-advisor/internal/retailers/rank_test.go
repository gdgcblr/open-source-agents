package retailers

import (
	"testing"
	"time"
)

var rankNow = time.Date(2026, 10, 24, 9, 30, 0, 0, time.UTC)

// mkOffer builds a usable offer with the given price/fees and ETA.
func mkOffer(r Retailer, price, deliveryFee, platformFee int64, eta int) Offer {
	return Offer{
		Retailer:    r,
		ProductName: "Coca-Cola 750ml",
		Price:       price,
		MRP:         price,
		DeliveryFee: deliveryFee,
		PlatformFee: platformFee,
		InStock:     true,
		Serviceable: true,
		ETAMinutes:  eta,
		Status:      StatusOK,
		Source:      SourceDemo,
		LastUpdated: rankNow,
	}
}

func TestRank(t *testing.T) {
	tests := []struct {
		name          string
		offers        []Offer
		memberships   []Membership
		wantBest      Retailer
		wantCheapest  Retailer
		wantFastest   Retailer
		wantExcluded  int
		wantHasUsable bool
	}{
		{
			name: "distinct costs and ETAs: best/cheapest = lowest cost, fastest = lowest ETA",
			offers: []Offer{
				mkOffer(RetailerInstamart, 4000, 3000, 600, 15), // 4000+3000+600 = 7600
				mkOffer(RetailerBlinkit, 4200, 2500, 500, 10),   // 4200+2500+500 = 7200
				mkOffer(RetailerZepto, 3800, 3500, 700, 20),     // 3800+3500+700 = 8000
				mkOffer(RetailerAmazon, 3600, 4000, 0, 1440),    // 3600+4000 = 7600
			},
			wantBest:      RetailerBlinkit,
			wantCheapest:  RetailerBlinkit,
			wantFastest:   RetailerBlinkit,
			wantExcluded:  0,
			wantHasUsable: true,
		},
		{
			name: "tie on cost: faster ETA wins for best",
			offers: []Offer{
				mkOffer(RetailerInstamart, 5000, 0, 0, 30),
				mkOffer(RetailerBlinkit, 5000, 0, 0, 12),
			},
			wantBest:      RetailerBlinkit,
			wantCheapest:  RetailerBlinkit,
			wantFastest:   RetailerBlinkit,
			wantExcluded:  0,
			wantHasUsable: true,
		},
		{
			name: "tie on cost and ETA: fewer fees win",
			offers: []Offer{
				mkOffer(RetailerInstamart, 4600, 0, 400, 12), // total 5000, fees 400
				mkOffer(RetailerBlinkit, 4800, 0, 200, 12),   // total 5000, fees 200
			},
			wantBest:      RetailerBlinkit,
			wantCheapest:  RetailerBlinkit,
			wantFastest:   RetailerBlinkit,
			wantExcluded:  0,
			wantHasUsable: true,
		},
		{
			name: "full tie: deterministic retailer-name order",
			offers: []Offer{
				mkOffer(RetailerInstamart, 5000, 0, 0, 12),
				mkOffer(RetailerBlinkit, 5000, 0, 0, 12),
			},
			wantBest:      RetailerBlinkit, // "blinkit" < "instamart"
			wantCheapest:  RetailerBlinkit,
			wantFastest:   RetailerBlinkit,
			wantExcluded:  0,
			wantHasUsable: true,
		},
		{
			name: "unusable offers excluded with reasons",
			offers: []Offer{
				mkOffer(RetailerInstamart, 4000, 0, 0, 15),
				func() Offer {
					o := mkOffer(RetailerBlinkit, 3000, 0, 0, 10)
					o.InStock = false
					return o
				}(),
				func() Offer {
					o := mkOffer(RetailerZepto, 3000, 0, 0, 8)
					o.Serviceable = false
					return o
				}(),
				func() Offer {
					o := mkOffer(RetailerAmazon, 3000, 0, 0, 1440)
					o.Status = StatusUnavailable
					o.StatusReason = "live source unavailable"
					return o
				}(),
			},
			wantBest:      RetailerInstamart,
			wantCheapest:  RetailerInstamart,
			wantFastest:   RetailerInstamart,
			wantExcluded:  3,
			wantHasUsable: true,
		},
		{
			name: "no usable offers: HasUsable false, everything excluded",
			offers: []Offer{
				func() Offer {
					o := mkOffer(RetailerBlinkit, 3000, 0, 0, 10)
					o.InStock = false
					return o
				}(),
				func() Offer {
					o := mkOffer(RetailerZepto, 3000, 0, 0, 8)
					o.Serviceable = false
					return o
				}(),
			},
			wantBest:      RetailerUnknown,
			wantCheapest:  RetailerUnknown,
			wantFastest:   RetailerUnknown,
			wantExcluded:  2,
			wantHasUsable: false,
		},
		{
			name: "membership free delivery flips ranking",
			// Instamart: 3800 + 2500 delivery = 6300, Blinkit: 5000 + 0 = 5000.
			// Without membership Blinkit wins; with Instamart One (fast tier ETA=12)
			// delivery fee drops to 0 → 3800, Instamart wins.
			offers: []Offer{
				mkOffer(RetailerInstamart, 3800, 2500, 0, 12),
				mkOffer(RetailerBlinkit, 5000, 0, 0, 10),
			},
			memberships:   []Membership{{ID: MembershipInstamartOne, Retailer: RetailerInstamart}},
			wantBest:      RetailerInstamart,
			wantCheapest:  RetailerInstamart,
			wantFastest:   RetailerBlinkit,
			wantExcluded:  0,
			wantHasUsable: true,
		},
		{
			name: "membership not applied on standard tier (mid ETA)",
			// ETA 30 → TierStandard, delivery fee not waived. Blinkit still cheaper.
			offers: []Offer{
				mkOffer(RetailerInstamart, 3800, 2500, 0, 30),
				mkOffer(RetailerBlinkit, 5000, 0, 0, 10),
			},
			memberships:   []Membership{{ID: MembershipInstamartOne, Retailer: RetailerInstamart}},
			wantBest:      RetailerBlinkit,
			wantCheapest:  RetailerBlinkit,
			wantFastest:   RetailerBlinkit,
			wantExcluded:  0,
			wantHasUsable: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			rec := Rank(tc.offers, tc.memberships, "560001", "coca-cola 750ml", rankNow)

			if rec.HasUsable != tc.wantHasUsable {
				t.Fatalf("HasUsable = %v, want %v", rec.HasUsable, tc.wantHasUsable)
			}
			if got := rec.Best.Retailer; got != tc.wantBest {
				t.Errorf("Best retailer = %v, want %v", got, tc.wantBest)
			}
			if got := rec.Cheapest.Retailer; got != tc.wantCheapest {
				t.Errorf("Cheapest retailer = %v, want %v", got, tc.wantCheapest)
			}
			if got := rec.Fastest.Retailer; got != tc.wantFastest {
				t.Errorf("Fastest retailer = %v, want %v", got, tc.wantFastest)
			}
			if got := len(rec.Excluded); got != tc.wantExcluded {
				t.Errorf("len(Excluded) = %d, want %d", got, tc.wantExcluded)
			}

			// Fixed now must be preserved (as UTC).
			if !rec.ComparedAt.Equal(rankNow) {
				t.Errorf("ComparedAt = %v, want %v", rec.ComparedAt, rankNow)
			}
			if len(rec.Explanations) == 0 {
				t.Errorf("expected at least one explanation line")
			}
		})
	}
}

// TestRankDeterminism runs the same offers through Rank repeatedly (and in
// shuffled input order) and asserts the outcome never changes.
func TestRankDeterminism(t *testing.T) {
	base := []Offer{
		mkOffer(RetailerInstamart, 4000, 3000, 600, 15),
		mkOffer(RetailerBlinkit, 4200, 2500, 500, 10),
		mkOffer(RetailerZepto, 3800, 3500, 700, 20),
		mkOffer(RetailerAmazon, 3600, 4000, 0, 1440),
	}
	first := Rank(base, nil, "560001", "q", rankNow)
	for i := 0; i < 10; i++ {
		// rotate input order
		shuffled := append(append([]Offer{}, base[i%len(base):]...), base[:i%len(base)]...)
		got := Rank(shuffled, nil, "560001", "q", rankNow)
		if got.Best.Retailer != first.Best.Retailer ||
			got.Cheapest.Retailer != first.Cheapest.Retailer ||
			got.Fastest.Retailer != first.Fastest.Retailer {
			t.Fatalf("run %d: ranking not deterministic: got best=%v fastest=%v, want best=%v fastest=%v",
				i, got.Best.Retailer, got.Fastest.Retailer, first.Best.Retailer, first.Fastest.Retailer)
		}
		if len(got.RankedOffers) != len(first.RankedOffers) {
			t.Fatalf("run %d: RankedOffers length changed", i)
		}
		for j := range got.RankedOffers {
			if got.RankedOffers[j].Retailer != first.RankedOffers[j].Retailer {
				t.Fatalf("run %d: RankedOffers[%d] = %v, want %v", i, j,
					got.RankedOffers[j].Retailer, first.RankedOffers[j].Retailer)
			}
		}
	}
}

// TestRankExcludedReasons verifies excluded offers keep their status/reason.
func TestRankExcludedReasons(t *testing.T) {
	offers := []Offer{
		mkOffer(RetailerInstamart, 4000, 0, 0, 15),
		func() Offer {
			o := mkOffer(RetailerBlinkit, 3000, 0, 0, 10)
			o.InStock = false
			return o
		}(),
		func() Offer {
			o := mkOffer(RetailerZepto, 3000, 0, 0, 8)
			o.Serviceable = false
			return o
		}(),
	}
	rec := Rank(offers, nil, "560001", "q", rankNow)
	if len(rec.Excluded) != 2 {
		t.Fatalf("len(Excluded) = %d, want 2", len(rec.Excluded))
	}
	statusByRetailer := map[Retailer]string{}
	for _, o := range rec.Excluded {
		statusByRetailer[o.Retailer] = o.Status
		if o.StatusReason == "" {
			t.Errorf("excluded offer %v has empty StatusReason", o.Retailer)
		}
	}
	if statusByRetailer[RetailerBlinkit] != StatusOutOfStock {
		t.Errorf("blinkit excluded status = %q, want %q", statusByRetailer[RetailerBlinkit], StatusOutOfStock)
	}
	if statusByRetailer[RetailerZepto] != StatusNotServiceable {
		t.Errorf("zepto excluded status = %q, want %q", statusByRetailer[RetailerZepto], StatusNotServiceable)
	}
}

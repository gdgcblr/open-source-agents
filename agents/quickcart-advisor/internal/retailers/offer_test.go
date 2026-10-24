package retailers

import (
	"strings"
	"testing"
	"time"
)

// baseUsableOffer returns a fully usable baseline offer; tests mutate copies.
func baseUsableOffer() Offer {
	return Offer{
		Retailer:    RetailerInstamart,
		ProductName: "Amul Taaza Milk 1L",
		Price:       2700, // ₹27.00
		MRP:         3000,
		Serviceable: true,
		InStock:     true,
		ETAMinutes:  12,
	}
}

func TestFormatINR(t *testing.T) {
	tests := []struct {
		name  string
		paise int64
		want  string
	}{
		{"zero", 0, "₹0.00"},
		{"paise only", 5, "₹0.05"},
		{"exactly one rupee", 100, "₹1.00"},
		{"rupees and paise", 123450, "₹1,234.50"},
		{"indian grouping 123456 rupees", 12345600, "₹1,23,456.00"},
		{"seven digits", 123456789, "₹12,34,567.89"},
		{"ten lakh grouping", 100000000, "₹10,00,000.00"},
		{"one crore grouping", 12345678900, "₹12,34,56,789.00"},
		{"no grouping under 1000", 99900, "₹999.00"},
		{"exactly 1000", 100000, "₹1,000.00"},
		{"exactly 100000 (lakh)", 10000000, "₹1,00,000.00"},
		{"negative paise", -50, "-₹0.50"},
		{"negative with grouping", -12345600, "-₹1,23,456.00"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := FormatINR(tt.paise); got != tt.want {
				t.Errorf("FormatINR(%d) = %q, want %q", tt.paise, got, tt.want)
			}
		})
	}
}

func TestComputeFees(t *testing.T) {
	tests := []struct {
		name       string
		mutate     func(*Offer)
		wantStatus string
		wantCost   int64
	}{
		{
			name: "usable: Price - Discount + fees + Taxes",
			mutate: func(o *Offer) {
				o.Price = 10000
				o.MRP = 10000
				o.Discount = 1000
				o.DeliveryFee = 3000
				o.PlatformFee = 500
				o.HandlingFee = 200
				o.SmallCartFee = 100
				o.OtherFees = 200
				o.Taxes = 500
			},
			wantStatus: StatusOK,
			wantCost:   10000 - 1000 + 3000 + 500 + 200 + 100 + 200 + 500, // 13500
		},
		{
			name: "usable: MRP-Price folded into Discount when none reported",
			mutate: func(o *Offer) {
				o.Price = 2700
				o.MRP = 3000
				o.DeliveryFee = 2500
			},
			wantStatus: StatusOK,
			// discount becomes 300, so total = 2700 - 300 + 2500 = 4900.
			wantCost: 4900,
		},
		{
			name: "usable: total clamped at zero",
			mutate: func(o *Offer) {
				o.Price = 100
				o.MRP = 100
				o.Discount = 99999
			},
			wantStatus: StatusOK,
			wantCost:   0,
		},
		{
			name: "not usable: not serviceable keeps cost 0",
			mutate: func(o *Offer) {
				o.Serviceable = false
			},
			wantStatus: StatusNotServiceable,
			wantCost:   0,
		},
		{
			name: "not usable: out of stock keeps cost 0",
			mutate: func(o *Offer) {
				o.InStock = false
			},
			wantStatus: StatusOutOfStock,
			wantCost:   0,
		},
		{
			name: "not usable: no price keeps cost 0",
			mutate: func(o *Offer) {
				o.Price = 0
				o.MRP = 3000
			},
			wantStatus: StatusUnavailable,
			wantCost:   0,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			o := baseUsableOffer()
			tt.mutate(&o)
			got := ComputeFees(o)
			if got.FinalDeliveredCost != tt.wantCost {
				t.Errorf("FinalDeliveredCost = %d, want %d", got.FinalDeliveredCost, tt.wantCost)
			}
			if got.Status != tt.wantStatus {
				t.Errorf("Status = %q, want %q", got.Status, tt.wantStatus)
			}
			if tt.wantStatus != StatusOK && got.StatusReason == "" {
				t.Errorf("StatusReason empty for unusable offer (status %q)", got.Status)
			}
		})
	}
}

func TestApplyMembership(t *testing.T) {
	onePass := []Membership{{ID: MembershipInstamartOne, Retailer: RetailerInstamart}}
	blinkitPass := []Membership{{ID: MembershipBlinkitPass, Retailer: RetailerBlinkit}}

	base := func() Offer {
		o := baseUsableOffer()
		o.Price = 10000
		o.MRP = 10000
		o.DeliveryFee = 3000
		o = ComputeFees(o)
		return o
	}

	t.Run("matching retailer on fast tier removes delivery fee", func(t *testing.T) {
		o := base() // ETA 12 -> fast
		got := ApplyMembership(o, onePass)
		if got.DeliveryFee != 0 {
			t.Errorf("DeliveryFee = %d, want 0", got.DeliveryFee)
		}
		if got.FinalDeliveredCost != 10000 {
			t.Errorf("FinalDeliveredCost = %d, want 10000", got.FinalDeliveredCost)
		}
		if !strings.Contains(got.MembershipBenefits, "free delivery") {
			t.Errorf("MembershipBenefits = %q, want mention of free delivery", got.MembershipBenefits)
		}
	})

	t.Run("matching retailer on slow tier removes delivery fee", func(t *testing.T) {
		o := base()
		o.ETAMinutes = 45 // slow boundary
		o = ComputeFees(o)
		got := ApplyMembership(o, onePass)
		if got.DeliveryFee != 0 {
			t.Errorf("DeliveryFee = %d, want 0", got.DeliveryFee)
		}
		if got.FinalDeliveredCost != 10000 {
			t.Errorf("FinalDeliveredCost = %d, want 10000", got.FinalDeliveredCost)
		}
	})

	t.Run("matching retailer on standard tier keeps delivery fee", func(t *testing.T) {
		o := base()
		o.ETAMinutes = 30 // standard (21..44)
		o = ComputeFees(o)
		got := ApplyMembership(o, onePass)
		if got.DeliveryFee != 3000 {
			t.Errorf("DeliveryFee = %d, want 3000 (standard tier excluded)", got.DeliveryFee)
		}
		if got.FinalDeliveredCost != 13000 {
			t.Errorf("FinalDeliveredCost = %d, want 13000", got.FinalDeliveredCost)
		}
		if !strings.Contains(got.MembershipBenefits, "no benefit") {
			t.Errorf("MembershipBenefits = %q, want mention of no benefit", got.MembershipBenefits)
		}
	})

	t.Run("non-matching retailer leaves offer untouched", func(t *testing.T) {
		o := base()
		got := ApplyMembership(o, blinkitPass)
		if got.DeliveryFee != 3000 {
			t.Errorf("DeliveryFee = %d, want 3000", got.DeliveryFee)
		}
		if got.FinalDeliveredCost != 13000 {
			t.Errorf("FinalDeliveredCost = %d, want 13000", got.FinalDeliveredCost)
		}
		if got.MembershipBenefits != "" {
			t.Errorf("MembershipBenefits = %q, want empty", got.MembershipBenefits)
		}
	})

	t.Run("unusable offer returned unchanged", func(t *testing.T) {
		o := baseUsableOffer()
		o.Serviceable = false
		o = ComputeFees(o)
		o.DeliveryFee = 3000
		got := ApplyMembership(o, onePass)
		if got.DeliveryFee != 3000 {
			t.Errorf("DeliveryFee = %d, want 3000 (offer unusable)", got.DeliveryFee)
		}
		if got.Status != StatusNotServiceable {
			t.Errorf("Status = %q, want %q", got.Status, StatusNotServiceable)
		}
	})

	t.Run("already free delivery keeps fee zero", func(t *testing.T) {
		o := baseUsableOffer()
		o.Price = 10000
		o.MRP = 10000
		o.DeliveryFee = 0
		o = ComputeFees(o)
		got := ApplyMembership(o, onePass)
		if got.DeliveryFee != 0 {
			t.Errorf("DeliveryFee = %d, want 0", got.DeliveryFee)
		}
		if got.FinalDeliveredCost != 10000 {
			t.Errorf("FinalDeliveredCost = %d, want 10000", got.FinalDeliveredCost)
		}
	})
}

func TestApplyMemberships(t *testing.T) {
	memberships := []Membership{
		{ID: MembershipInstamartOne, Retailer: RetailerInstamart},
		{ID: MembershipBlinkitPass, Retailer: RetailerBlinkit},
	}
	offers := []Offer{
		{Retailer: RetailerInstamart, Price: 10000, MRP: 10000, DeliveryFee: 3000, Serviceable: true, InStock: true, ETAMinutes: 12, Status: StatusOK},
		{Retailer: RetailerBlinkit, Price: 10000, MRP: 10000, DeliveryFee: 2500, Serviceable: true, InStock: true, ETAMinutes: 10, Status: StatusOK},
		{Retailer: RetailerZepto, Price: 10000, MRP: 10000, DeliveryFee: 2000, Serviceable: true, InStock: true, ETAMinutes: 16, Status: StatusOK},
	}
	for i := range offers {
		offers[i] = ComputeFees(offers[i])
	}
	got := ApplyMemberships(offers, memberships)
	if len(got) != len(offers) {
		t.Fatalf("len(got) = %d, want %d", len(got), len(offers))
	}
	if got[0].DeliveryFee != 0 {
		t.Errorf("instamart DeliveryFee = %d, want 0", got[0].DeliveryFee)
	}
	if got[1].DeliveryFee != 0 {
		t.Errorf("blinkit DeliveryFee = %d, want 0", got[1].DeliveryFee)
	}
	if got[2].DeliveryFee != 2000 {
		t.Errorf("zepto DeliveryFee = %d, want 2000 (no zepto membership)", got[2].DeliveryFee)
	}
	if got[2].FinalDeliveredCost != 12000 {
		t.Errorf("zepto FinalDeliveredCost = %d, want 12000", got[2].FinalDeliveredCost)
	}
	// Input slice must not be mutated.
	if offers[0].DeliveryFee != 3000 {
		t.Errorf("input slice mutated: offers[0].DeliveryFee = %d, want 3000", offers[0].DeliveryFee)
	}
}

func TestKnownServiceability(t *testing.T) {
	now := time.Date(2026, 10, 24, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name         string
		retailer     Retailer
		pincode      string
		wantServ     bool
		wantETA      int
		wantReasonTo string // substring expected in Reason
	}{
		{"instamart known metro delhi", RetailerInstamart, "110001", true, 12, "dark stores"},
		{"blinkit known metro mumbai", RetailerBlinkit, "400001", true, 10, "dark stores"},
		{"zepto known metro bengaluru", RetailerZepto, "560001", true, 16, "dark stores"},
		{"instamart unknown prefix", RetailerInstamart, "999999", false, 0, "no Swiggy Instamart dark-store zone"},
		{"amazon unknown prefix still serviceable slow", RetailerAmazon, "999999", true, 3 * minutesPerDay, "slower"},
		{"amazon known prefix next-day", RetailerAmazon, "110001", true, minutesPerDay, "next-day"},
		{"invalid pincode too short", RetailerInstamart, "1100", false, 0, "not a valid 6-digit"},
		{"invalid pincode non-numeric", RetailerInstamart, "11A001", false, 0, "not a valid 6-digit"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := KnownServiceability(tt.retailer, tt.pincode, now)
			if got.Serviceable != tt.wantServ {
				t.Errorf("Serviceable = %v, want %v (reason: %q)", got.Serviceable, tt.wantServ, got.Reason)
			}
			if got.ETAMinutes != tt.wantETA {
				t.Errorf("ETAMinutes = %d, want %d", got.ETAMinutes, tt.wantETA)
			}
			if !strings.Contains(got.Reason, tt.wantReasonTo) {
				t.Errorf("Reason = %q, want substring %q", got.Reason, tt.wantReasonTo)
			}
			if got.Source != SourceDemo {
				t.Errorf("Source = %q, want %q", got.Source, SourceDemo)
			}
			if !got.IsEstimate {
				t.Errorf("IsEstimate = false, want true for catalog answer")
			}
			if got.PINCode != tt.pincode || got.Retailer != tt.retailer {
				t.Errorf("identity fields wrong: got %s/%v", got.PINCode, got.Retailer)
			}
		})
	}
}

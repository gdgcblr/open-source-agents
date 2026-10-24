package retailers

import (
	"fmt"
	"strings"
	"time"
)

// FormatINR formats an integer paise amount as Indian Rupees (e.g. ₹1,234.50).
func FormatINR(paise int64) string {
	negative := paise < 0
	if negative {
		paise = -paise
	}
	rupees := paise / 100
	p := paise % 100

	// Indian digit grouping: last 3 digits, then groups of 2.
	s := fmt.Sprintf("%d", rupees)
	var b strings.Builder
	n := len(s)
	for i, c := range s {
		rem := n - i
		if i > 0 && rem > 3 && (rem-3)%2 == 0 {
			b.WriteByte(',')
		} else if i > 0 && rem == 3 {
			b.WriteByte(',')
		}
		b.WriteRune(c)
	}
	sign := ""
	if negative {
		sign = "-"
	}
	return fmt.Sprintf("%s₹%s.%02d", sign, b.String(), p)
}

// ComputeFees normalizes a raw offer into a fully costed one:
//   - If the offer is not usable (not serviceable / out of stock / unavailable
//     / missing data), FinalDeliveredCost stays 0 and Status+StatusReason explain.
//   - FinalDeliveredCost = Price − Discount + fees + taxes (clamped at ≥ 0).
//   - Item-level savings (MRP − Price) are folded into Discount when the
//     source did not already report one, so the total is never overstated.
func ComputeFees(o Offer) Offer {
	if o.Status == "" {
		o.Status = StatusOK
	}
	if o.Source == "" {
		o.Source = SourceDemo
	}
	switch {
	case !o.Serviceable:
		o.Status = StatusNotServiceable
		if o.StatusReason == "" {
			o.StatusReason = "no fulfillment option available for this pincode"
		}
		return o
	case !o.InStock:
		o.Status = StatusOutOfStock
		if o.StatusReason == "" {
			o.StatusReason = "listed but currently out of stock"
		}
		return o
	case o.Price <= 0:
		o.Status = StatusUnavailable
		if o.StatusReason == "" {
			o.StatusReason = "no price data available"
		}
		return o
	}

	// When the per-unit selling price is below MRP and no explicit discount
	// was reported, attribute the difference to the discount so the total
	// equals Price + fees (never MRP + fees).
	discount := o.Discount
	if discount <= 0 && o.MRP > o.Price {
		discount = o.MRP - o.Price
	}

	total := o.Price - discount + o.Fees().Total() + o.Taxes
	if total < 0 {
		total = 0
	}
	o.Discount = discount
	o.FinalDeliveredCost = total
	return o
}

// ApplyMembership returns a copy of the offer with membership benefits
// applied. Exactly one membership applies per retailer (the first match).
//
// Rules (mirroring quick-commerce reality):
//   - Delivery fee becomes free with the retailer's membership pass, but only
//     on Fast (≤ 20 min) or Slow (≥ 45 min, including multi-day Amazon)
//     deliveries — mid-range Standard deliveries are excluded.
//   - No membership ever removes platform/handling/small-cart/taxes.
//   - Applying a membership recomputes FinalDeliveredCost.
func ApplyMembership(o Offer, m []Membership) Offer {
	if !o.Serviceable || !o.InStock || o.Status != StatusOK {
		return o
	}
	for _, mem := range m {
		if mem.Retailer != o.Retailer {
			continue
		}
		tier := o.Tier()
		if o.DeliveryFee > 0 && (tier == TierFast || tier == TierSlow) {
			o.DeliveryFee = 0
			o.MembershipBenefits = fmt.Sprintf("%s: free delivery (%s delivery)", MembershipLabel(mem.ID), tier.String())
		} else if o.DeliveryFee > 0 {
			o.MembershipBenefits = fmt.Sprintf("%s: no benefit on %s delivery", MembershipLabel(mem.ID), tier.String())
		} else {
			o.MembershipBenefits = fmt.Sprintf("%s: delivery already free", MembershipLabel(mem.ID))
		}
		return ComputeFees(o)
	}
	return o
}

// ApplyMemberships applies the membership set to every offer in a slice.
func ApplyMemberships(offers []Offer, m []Membership) []Offer {
	out := make([]Offer, len(offers))
	for i, o := range offers {
		out[i] = ApplyMembership(o, m)
	}
	return out
}

// metroQComETAs are the demo fast-delivery ETAs (minutes) for fulfilled
// quick-commerce dark-store zones, keyed by retailer.
var metroQComETAs = map[Retailer]int{
	RetailerInstamart: 12,
	RetailerBlinkit:   10,
	RetailerZepto:     16,
	RetailerAmazon:    minutesPerDay, // next-day for Prime-eligible items
}

// metroQComPrefixes are the pincode first-two-digit prefixes of metro /
// large-city regions where Instamart, Blinkit and Zepto operate dark stores
// (demo data, sourced from the offline catalog knowledge).
var metroQComPrefixes = map[string]bool{
	"11": true, // Delhi
	"40": true, // Mumbai
	"56": true, // Bengaluru
	"60": true, // Chennai
	"50": true, // Hyderabad
	"41": true, // Pune
	"70": true, // Kolkata
	"38": true, // Ahmedabad
	"20": true, // part of UP (Noida/Ghaziabad side demo zones)
	"12": true, // Gurugram/Faridabad (NCR)
}

// amazonPrefixes are the pincode first-two-digit prefixes with broad Amazon
// India next-day / same-day coverage (demo data). Amazon covers essentially
// every Indian pincode; the distinction here is only between "next-day
// Prime-speed" and slower standard delivery.
var amazonFastPrefixes = map[string]bool{
	"11": true, "40": true, "56": true, "60": true,
	"50": true, "41": true, "70": true, "38": true,
	"12": true, "20": true, "68": true, "69": true,
	"30": true, "36": true, "44": true, "48": true,
}

// validPincode reports whether s looks like an Indian 6-digit PIN code.
func validPincode(s string) bool {
	if len(s) != 6 {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return s[0] != '0'
}

// KnownServiceability answers check_serviceability from the offline catalog
// of zones. Every answer is labeled SourceDemo and IsEstimate=true unless it
// came from a live source. Unknown pincodes are reported not serviceable with
// an explicit reason — never guessed as serviceable.
func KnownServiceability(r Retailer, pincode string, now time.Time) ServiceabilityResult {
	res := ServiceabilityResult{
		Retailer:   r,
		PINCode:    pincode,
		IsEstimate: true,
		Source:     SourceDemo,
		CheckedAt:  now.UTC(),
	}
	if !validPincode(pincode) {
		res.Serviceable = false
		res.Reason = fmt.Sprintf("%q is not a valid 6-digit Indian PIN code", pincode)
		return res
	}
	prefix := pincode[:2]

	if r == RetailerAmazon {
		res.Serviceable = true
		if amazonFastPrefixes[prefix] {
			res.ETAMinutes = minutesPerDay // ~next day
			res.Reason = "Amazon India delivers here; standard demo estimate of next-day delivery for Prime-eligible items"
		} else {
			res.ETAMinutes = 3 * minutesPerDay
			res.Reason = "Amazon India likely delivers here with a slower (multi-day) estimate; demo catalog has no live zone data"
		}
		return res
	}

	if eta, ok := metroQComETAs[r]; ok && metroQComPrefixes[prefix] {
		res.Serviceable = true
		res.ETAMinutes = eta
		res.Reason = fmt.Sprintf("offline demo zone: %s operates dark stores in this metro prefix (estimated %d min delivery)", r.DisplayName(), eta)
		return res
	}
	res.Serviceable = false
	res.Reason = fmt.Sprintf("offline demo catalog has no %s dark-store zone for pincode prefix %q; likely not serviceable", r.DisplayName(), prefix)
	return res
}

// ServiceabilityHub resolves serviceability: try the live source first for
// the quick-commerce retailers, fall back to the offline catalog, and blend
// the two so a live "yes/no" answer is never silently discarded. The result
// always carries its Source label.
type ServiceabilityHub struct {
	// Live may be nil; when set it is consulted first for the three
	// quick-commerce retailers.
	Live DataSource
}

// Check returns the best-known serviceability answer. TryFulfill results and
// catalog knowledge are blended: a live success wins; a live failure for a
// quick-commerce retailer marks the answer "unavailable" unless the demo
// catalog knows a zone (then it is clearly labeled an estimate).
func (h ServiceabilityHub) Check(r Retailer, pincode string, now time.Time) ServiceabilityResult {
	base := KnownServiceability(r, pincode, now)
	if h.Live == nil || r == RetailerAmazon {
		return base // qbuys covers only the 3 quick-commerce sites; Amazon is always catalog-based.
	}
	if !base.Serviceable {
		return base // not even a valid/known zone — don't bother the network.
	}
	liveResult := h.Live.TryFulfill(pincode, now)
	if liveResult == nil {
		base.Reason += " (live qbuys source unreachable; answer is a demo estimate)"
		return base
	}
	if live, ok := liveResult[r]; ok {
		if live.Offer != nil {
			base.Source = SourceQBuysLive
			base.IsEstimate = false
			base.Reason = fmt.Sprintf("confirmed serviceable by live qbuys fulfillment for %s", r.DisplayName())
			return base
		}
		if live.Reason != "" {
			base.Source = SourceQBuysLive
			base.IsEstimate = false
			base.Serviceable = false
			base.ETAMinutes = 0
			base.Reason = fmt.Sprintf("live qbuys fulfillment failed for %s: %s", r.DisplayName(), live.Reason)
			return base
		}
	}
	base.Reason += " (no live qbuys data for this retailer; answer is a demo estimate)"
	return base
}

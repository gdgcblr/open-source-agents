package retailers

import (
	"fmt"
	"sort"
	"time"
)

// usableOffer reports whether an offer can participate in ranking.
func usableOffer(o Offer) bool {
	return o.Status == StatusOK && o.InStock && o.Serviceable && o.FinalDeliveredCost > 0
}

func compareOffers(a, b Offer) int {
	if a.FinalDeliveredCost != b.FinalDeliveredCost {
		if a.FinalDeliveredCost < b.FinalDeliveredCost {
			return -1
		}
		return 1
	}
	if a.ETAMinutes != b.ETAMinutes {
		if a.ETAMinutes < b.ETAMinutes {
			return -1
		}
		return 1
	}
	if fa, fb := a.Fees().Total(), b.Fees().Total(); fa != fb {
		if fa < fb {
			return -1
		}
		return 1
	}
	// Deterministic final tie-break so ordering is stable across runs.
	return compareString(a.Retailer.String(), b.Retailer.String())
}

func compareString(a, b string) int {
	if a < b {
		return -1
	}
	if a > b {
		return 1
	}
	return 0
}

// Rank deterministically ranks offers:
//   - usable = InStock && Serviceable && Status == StatusOK, after the
//     membership set has been applied to a copy of each offer.
//   - Best = lowest FinalDeliveredCost, tie-break faster ETA, then fewer fees.
//   - Cheapest = lowest FinalDeliveredCost (identical to Best by construction,
//     both fields are kept explicit for the report).
//   - Fastest = lowest ETAMinutes among usable offers, tie-break lower cost.
//
// Excluded offers (unavailable / out of stock / not serviceable) are kept in
// Excluded with their StatusReason, so the agent can state plainly why a
// retailer is missing instead of guessing.
func Rank(offers []Offer, memberships []Membership, pincode, query string, now time.Time) Recommendation {
	rec := Recommendation{
		ComparedAt: now.UTC(),
		PINCode:    pincode,
		Query:      query,
	}
	var usable []Offer
	for _, raw := range offers {
		o := ApplyMembership(ComputeFees(raw), memberships)
		if usableOffer(o) {
			usable = append(usable, o)
		} else {
			rec.Excluded = append(rec.Excluded, o)
		}
	}
	if len(usable) == 0 {
		rec.Explanations = append(rec.Explanations,
			"No retailer returned an in-stock, serviceable offer for this product and pincode; nothing to rank.")
		return rec
	}

	sort.SliceStable(usable, func(i, j int) bool { return compareOffers(usable[i], usable[j]) < 0 })
	rec.HasUsable = true
	rec.RankedOffers = usable
	rec.Best = usable[0]
	rec.Cheapest = usable[0]

	// Fastest: min ETA among usable; tie-break lower cost.
	fastest := usable[0]
	for _, o := range usable[1:] {
		if fastest.ETAMinutes <= 0 || (o.ETAMinutes > 0 && o.ETAMinutes < fastest.ETAMinutes) ||
			(o.ETAMinutes == fastest.ETAMinutes && o.FinalDeliveredCost < fastest.FinalDeliveredCost) {
			fastest = o
		}
	}
	rec.Fastest = fastest

	rec.Explanations = buildExplanations(rec, memberships)
	return rec
}

func describeOffer(o Offer) string {
	return fmt.Sprintf("%s (%s)", o.Retailer.DisplayName(), FormatINR(o.FinalDeliveredCost))
}

func buildExplanations(rec Recommendation, memberships []Membership) []string {
	var lines []string
	best := rec.Best

	lines = append(lines, fmt.Sprintf("Best total: %s, delivered in %s.",
		describeOffer(best), describeETA(best.ETAMinutes)))

	// Savings vs runner-up.
	if len(rec.RankedOffers) > 1 {
		runnerUp := rec.RankedOffers[1]
		savings := runnerUp.FinalDeliveredCost - best.FinalDeliveredCost
		switch {
		case savings > 0:
			lines = append(lines, fmt.Sprintf("Saves %s vs the next best option, %s.",
				FormatINR(savings), describeOffer(runnerUp)))
		case savings == 0 && best.ETAMinutes <= runnerUp.ETAMinutes:
			lines = append(lines, fmt.Sprintf("Tied on price with %s; %s wins on faster delivery.",
				runnerUp.Retailer.DisplayName(), best.Retailer.DisplayName()))
		}
	}

	// Delivery-speed trade-off between Best and Fastest.
	if rec.Fastest.Retailer != best.Retailer {
		costDiff := rec.Fastest.FinalDeliveredCost - best.FinalDeliveredCost
		lines = append(lines, fmt.Sprintf("Trade-off: %s is fastest (%s) but costs %s more than %s (%s).",
			rec.Fastest.Retailer.DisplayName(), describeETA(rec.Fastest.ETAMinutes),
			FormatINR(costDiff), best.Retailer.DisplayName(), describeETA(best.ETAMinutes)))
	}

	// Fee note: highlight when fees are a large share of the total.
	if fees := best.Fees().Total() + best.Taxes; fees > 0 && fees*100 >= best.FinalDeliveredCost*15 {
		lines = append(lines, fmt.Sprintf("Fee note: %s adds %s in fees/taxes (%s of the total).",
			best.Retailer.DisplayName(), FormatINR(fees), percent(fees, best.FinalDeliveredCost)))
	}

	// Membership note.
	if best.MembershipBenefits != "" {
		lines = append(lines, fmt.Sprintf("Membership applied: %s.", best.MembershipBenefits))
	} else if len(memberships) > 0 {
		lines = append(lines, "Your memberships did not reduce the winning offer's fees.")
	}

	// Data-source caveat for the winning offer.
	if best.Source == SourceDemo {
		lines = append(lines, fmt.Sprintf("Data caveat: the winning %s offer comes from the offline demo catalog, not a live source — verify on the app before buying.", best.Retailer.DisplayName()))
	}

	// Excluded retailers, plainly stated.
	for _, o := range rec.Excluded {
		reason := o.StatusReason
		if reason == "" {
			reason = o.Status
		}
		lines = append(lines, fmt.Sprintf("%s could not be ranked: %s.", o.Retailer.DisplayName(), reason))
	}
	return lines
}

func percent(part, whole int64) string {
	if whole <= 0 {
		return "0%"
	}
	return fmt.Sprintf("%d%%", part*100/whole)
}

func describeETA(min int) string {
	switch {
	case min <= 0:
		return "unknown delivery time"
	case min < 60:
		return fmt.Sprintf("%d min", min)
	case min < minutesPerDay:
		return fmt.Sprintf("~%d h", (min+30)/60)
	case min%minutesPerDay == 0:
		d := min / minutesPerDay
		if d == 1 {
			return "~1 day"
		}
		return fmt.Sprintf("~%d days", d)
	default:
		d := (min + minutesPerDay - 1) / minutesPerDay
		return fmt.Sprintf("~%d days", d)
	}
}

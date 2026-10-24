package retailers

import (
	"context"
	"fmt"
	"regexp"
	"strings"
	"time"
)

// CatalogSource is the always-available offline demo catalog. Every offer it
// returns is labeled SourceDemo with LastUpdated set at call time, so demo
// data is never mistaken for live data. All numbers are plausible Indian
// quick-commerce figures, but they are samples — not real prices.
type CatalogSource struct{}

var _ DataSource = CatalogSource{}

// Name implements DataSource.
func (CatalogSource) Name() string { return SourceDemo }

// Retailers implements DataSource — the catalog covers all four retailers,
// and Amazon is always served from here.
func (CatalogSource) Retailers() []Retailer { return AllRetailers }

// TryFulfill implements DataSource: the catalog has no live fulfillment
// probe, so it reports catalog serviceability knowledge per retailer.
func (CatalogSource) TryFulfill(pincode string, now time.Time) map[Retailer]FulfillmentResult {
	out := make(map[Retailer]FulfillmentResult, len(AllRetailers))
	for _, r := range AllRetailers {
		svc := KnownServiceability(r, pincode, now)
		out[r] = FulfillmentResult{Retailer: r, Reason: svc.Reason, CheckedAt: now.UTC()}
	}
	return out
}

// Lookup implements DataSource. It fuzzy-matches the query against the demo
// catalog and returns one offer per retailer (unavailable offers where the
// catalog has no entry or the pincode is not serviceable).
func (c CatalogSource) Lookup(_ context.Context, q SearchQuery) ([]Offer, error) {
	now := time.Now().UTC()
	entry, _, ok := c.FindProduct(q.ProductName)
	if !ok && q.Brand == "" && q.Quantity == "" {
		return nil, fmt.Errorf("offline demo catalog has no product matching %q", q.ProductName)
	}

	offers := make([]Offer, 0, len(AllRetailers))
	for _, r := range AllRetailers {
		svc := KnownServiceability(r, q.PINCode, now)
		base := Offer{
			Retailer:     r,
			Source:       SourceDemo,
			LastUpdated:  now,
			ProductURL:   demoProductURL(r, entry),
			CheckoutURL:  demoProductURL(r, entry),
			Status:       StatusOK,
			ETAMinutes:   svc.ETAMinutes,
			Serviceable:  svc.Serviceable,
			StatusReason: svc.Reason,
		}
		if !ok {
			base.ProductName = q.ProductName
			base.Brand = q.Brand
			base.Quantity = q.Quantity
			base.Serviceable = false
			base.Status = StatusUnavailable
			base.StatusReason = fmt.Sprintf("offline demo catalog has no product matching %q", q.ProductName)
			offers = append(offers, base)
			continue
		}
		base.ProductName = entry.Name
		base.Brand = entry.Brand
		base.Variant = entry.Variant
		base.Quantity = entry.Quantity

		price, found := entry.Prices[r]
		if !found {
			base.Serviceable = false
			base.Status = StatusUnavailable
			base.StatusReason = fmt.Sprintf("offline demo catalog does not track %q on %s", entry.Name, r.DisplayName())
			offers = append(offers, base)
			continue
		}
		base.Price = price.Price
		base.MRP = price.MRP
		base.InStock = price.InStock
		if !price.InStock {
			base.Status = StatusOutOfStock
			base.StatusReason = "out of stock in the offline demo catalog"
		}
		applyDemoFees(&base, r)
		offers = append(offers, base)
	}
	return offers, nil
}

// FindProduct fuzzy-matches free text against the catalog. It returns the
// entry and a match confidence in [0,1].
func (CatalogSource) FindProduct(input string) (*CatalogEntry, float64, bool) {
	input = strings.ToLower(strings.TrimSpace(input))
	if input == "" {
		return nil, 0, false
	}
	type scored struct {
		entry *CatalogEntry
		score float64
	}
	var best scored
	for i := range catalogEntries {
		e := &catalogEntries[i]
		s := matchScore(input, e)
		if s > best.score {
			best = scored{entry: e, score: s}
		}
	}
	if best.entry == nil || best.score < 0.30 {
		return nil, 0, false
	}
	return best.entry, best.score, true
}

// matchScore scores how well free text matches a catalog entry: keyword
// overlap plus brand/alias bonuses. Deterministic, no randomness.
func matchScore(input string, e *CatalogEntry) float64 {
	keywords := strings.Fields(strings.ToLower(e.Keywords))
	if len(keywords) == 0 {
		return 0
	}
	hits := 0
	for _, kw := range keywords {
		if strings.Contains(input, kw) {
			hits++
		}
	}
	score := float64(hits) / float64(len(keywords))
	if hits == 0 {
		return 0
	}
	if strings.Contains(input, strings.ToLower(e.Brand)) {
		score += 0.20
	}
	for _, alias := range e.Aliases {
		if strings.Contains(input, strings.ToLower(alias)) {
			score += 0.15
			break
		}
	}
	if score > 1 {
		score = 1
	}
	return score
}

// CatalogEntry is one demo-catalog product with per-retailer pricing.
type CatalogEntry struct {
	ID       string
	Name     string
	Brand    string
	Variant  string
	Quantity string
	Category string
	Keywords string // space-separated matchable tokens, lowercase
	Aliases  []string
	Prices   map[Retailer]CatalogPrice
}

// CatalogPrice is a per-retailer demo price record.
type CatalogPrice struct {
	Price   int64 // paise
	MRP     int64 // paise
	InStock bool
}

// applyDemoFees fills the demo fee structure for a retailer. Quick-commerce
// orders add small-cart fees below a basket threshold; Amazon adds delivery
// for non-Prime members. All clearly demo values.
func applyDemoFees(o *Offer, r Retailer) {
	switch r {
	case RetailerInstamart:
		o.PlatformFee = 600
		o.HandlingFee = 199
		if o.Price < 19900 {
			o.SmallCartFee = 3000
		}
		o.DeliveryFee = 3000
	case RetailerBlinkit:
		o.PlatformFee = 400
		o.HandlingFee = 149
		if o.Price < 19900 {
			o.SmallCartFee = 2500
		}
		o.DeliveryFee = 2500
	case RetailerZepto:
		o.PlatformFee = 999
		o.HandlingFee = 99
		if o.Price < 29900 {
			o.SmallCartFee = 2000
		}
		o.DeliveryFee = 3000
	case RetailerAmazon:
		// Fresh-style: no platform fee; delivery fee unless the basket is big.
		if o.Price < 49900 {
			o.DeliveryFee = 4000
		}
	}
}

// demoProductURL builds the catalog-determined product page URL. These are
// search/deep links into each retailer's public app or site; they are demo
// navigational links, not live inventory lookups.
func demoProductURL(r Retailer, e *CatalogEntry) string {
	if e == nil {
		return ""
	}
	slug := strings.ToLower(regexp.MustCompile(`[^a-z0-9]+`).ReplaceAllString(e.Name, "-"))
	slug = strings.Trim(slug, "-")
	switch r {
	case RetailerInstamart:
		return fmt.Sprintf("https://www.swiggy.com/instamart/search?query=%s", strings.ReplaceAll(slug, "-", "%20"))
	case RetailerBlinkit:
		return fmt.Sprintf("https://blinkit.com/s/?q=%s", strings.ReplaceAll(slug, "-", "%20"))
	case RetailerZepto:
		return fmt.Sprintf("https://www.zeptonow.com/search?query=%s", strings.ReplaceAll(slug, "-", "%20"))
	case RetailerAmazon:
		return fmt.Sprintf("https://www.amazon.in/s?k=%s", strings.ReplaceAll(slug, "-", "+"))
	default:
		return ""
	}
}

// ToProduct converts a catalog entry into the normalized Product identity.
func (e *CatalogEntry) ToProduct(sourceURL string) *Product {
	if e == nil {
		return nil
	}
	return &Product{
		ID:           e.ID,
		Name:         e.Name,
		Brand:        e.Brand,
		Variant:      e.Variant,
		Quantity:     e.Quantity,
		Category:     e.Category,
		SourceURL:    sourceURL,
		CanonicalKey: e.ID,
		Source:       SourceDemo,
	}
}

// price is a small constructor for demo CatalogPrice values (price/MRP in
// whole rupees, for readability of the sample data).
func price(priceINR, mrpINR int64, inStock bool) CatalogPrice {
	return CatalogPrice{Price: priceINR * 100, MRP: mrpINR * 100, InStock: inStock}
}

// catalogEntries is the deterministic demo catalog: common Indian
// quick-commerce staples, all four retailers, realistic sample pricing.
// These are illustrative numbers for a runnable zero-network comparison —
// SourceDemo is stamped on everything produced from them.
var catalogEntries = []CatalogEntry{
	{
		ID: "amul-taaza-milk-1l", Name: "Amul Taaza Toned Fresh Milk 1L (Pouch)", Brand: "Amul",
		Variant: "Toned", Quantity: "1 L", Category: "Dairy",
		Keywords: "amul taaza milk 1l toned pouch",
		Aliases:  []string{"amul milk", "taaza milk", "milk 1 litre", "amul taaza"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(68, 70, true),
			RetailerBlinkit:   price(66, 70, true),
			RetailerZepto:     price(67, 70, true),
			RetailerAmazon:    price(69, 70, false), // dairy rarely on Amazon Fresh demo list
		},
	},
	{
		ID: "britannia-whole-wheat-bread-400g", Name: "Britannia 100% Whole Wheat Bread 400g", Brand: "Britannia",
		Variant: "Whole Wheat", Quantity: "400 g", Category: "Bakery",
		Keywords: "britannia whole wheat bread 400g",
		Aliases:  []string{"brown bread", "wheat bread", "britannia bread"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(45, 50, true),
			RetailerBlinkit:   price(48, 50, true),
			RetailerZepto:     price(45, 50, true),
			RetailerAmazon:    price(50, 50, true),
		},
	},
	{
		ID: "maggi-noodles-420g", Name: "Maggi 2-Minute Masala Noodles 420g (Pack of 6)", Brand: "Maggi",
		Variant: "Masala", Quantity: "420 g", Category: "Instant Food",
		Keywords: "maggi noodles masala 420g pack",
		Aliases:  []string{"maggi", "noodles", "maggi family pack", "2 minute noodles"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(83, 96, true),
			RetailerBlinkit:   price(85, 96, true),
			RetailerZepto:     price(89, 96, true),
			RetailerAmazon:    price(80, 96, true),
		},
	},
	{
		ID: "coca-cola-750ml", Name: "Coca-Cola Soft Drink 750ml Bottle", Brand: "Coca-Cola",
		Variant: "Original", Quantity: "750 ml", Category: "Beverages",
		Keywords: "coca cola coke soft drink 750ml",
		Aliases:  []string{"coke", "coca cola", "coke bottle"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(40, 45, true),
			RetailerBlinkit:   price(38, 45, true),
			RetailerZepto:     price(40, 45, true),
			RetailerAmazon:    price(42, 45, true),
		},
	},
	{
		ID: "lays-magic-masala-73g", Name: "Lay's India's Magic Masala Chips 73g", Brand: "Lay's",
		Variant: "Magic Masala", Quantity: "73 g", Category: "Snacks",
		Keywords: "lays magic masala chips 73g",
		Aliases:  []string{"lays", "lay's", "chips", "blue lays"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(20, 20, true),
			RetailerBlinkit:   price(20, 20, true),
			RetailerZepto:     price(20, 20, false),
			RetailerAmazon:    price(30, 30, true), // multipack-only demo listing
		},
	},
	{
		ID: "tata-salt-1kg", Name: "Tata Salt Iodised 1kg", Brand: "Tata",
		Variant: "Iodised", Quantity: "1 kg", Category: "Staples",
		Keywords: "tata salt iodised 1kg",
		Aliases:  []string{"salt", "namak", "tata namak"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(30, 30, true),
			RetailerBlinkit:   price(30, 30, true),
			RetailerZepto:     price(28, 30, true),
			RetailerAmazon:    price(28, 30, true),
		},
	},
	{
		ID: "aashirvaad-atta-5kg", Name: "Aashirvaad Shudh Chakki Atta 5kg", Brand: "Aashirvaad",
		Variant: "Whole Wheat", Quantity: "5 kg", Category: "Staples",
		Keywords: "aashirvaad atta wheat flour 5kg chakki",
		Aliases:  []string{"atta", "flour", "wheat flour", "ashirwad atta"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(227, 285, true),
			RetailerBlinkit:   price(232, 285, true),
			RetailerZepto:     price(235, 285, false),
			RetailerAmazon:    price(215, 285, true),
		},
	},
	{
		ID: "nescafe-classic-50g", Name: "Nescafe Classic Instant Coffee 50g Jar", Brand: "Nescafe",
		Variant: "Classic", Quantity: "50 g", Category: "Beverages",
		Keywords: "nescafe classic instant coffee 50g jar",
		Aliases:  []string{"coffee", "nescafe", "instant coffee"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(155, 175, true),
			RetailerBlinkit:   price(149, 175, true),
			RetailerZepto:     price(150, 175, true),
			RetailerAmazon:    price(140, 175, true),
		},
	},
	{
		ID: "amul-butter-500g", Name: "Amul Salted Butter 500g", Brand: "Amul",
		Variant: "Salted", Quantity: "500 g", Category: "Dairy",
		Keywords: "amul butter salted 500g",
		Aliases:  []string{"butter", "amul butter", "makhan"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(265, 275, true),
			RetailerBlinkit:   price(260, 275, true),
			RetailerZepto:     price(270, 275, true),
			RetailerAmazon:    price(275, 275, false),
		},
	},
	{
		ID: "fresh-onion-1kg", Name: "Fresh Onion (Loose) 1kg", Brand: "Fresh",
		Variant: "Loose", Quantity: "1 kg", Category: "Vegetables",
		Keywords: "fresh onion loose 1kg vegetables",
		Aliases:  []string{"onion", "pyaz", "kanda", "onion 1kg"},
		Prices: map[Retailer]CatalogPrice{
			RetailerInstamart: price(38, 45, true),
			RetailerBlinkit:   price(35, 45, true),
			RetailerZepto:     price(42, 45, true),
			RetailerAmazon:    price(40, 45, true),
		},
	},
}

var nonDigitOrLetter = regexp.MustCompile(`[^a-z0-9]+`)

// slugify turns free text into a stable slug suitable for catalog IDs.
func slugify(s string) string {
	return strings.Trim(nonDigitOrLetter.ReplaceAllString(strings.ToLower(s), "-"), "-")
}

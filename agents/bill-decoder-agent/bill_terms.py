"""
Reference notes on common Indian utility bill terms.

Added to the prompt so Gemini explains these terms correctly and consistently,
instead of guessing what an abbreviation stands for.
"""

TERM_NOTES = """
Reference notes on common bill terms (use these when a term on the bill matches;
for other terms explain from general knowledge and say "usually" if unsure):

ELECTRICITY (e.g. BESCOM, MESCOM, HESCOM, TANGEDCO, MSEDCL)
- Fixed Charges: a monthly charge for keeping the connection ready, based on the
  sanctioned load (kW), paid even if you use no power. Reduce it only by lowering
  the sanctioned load if it is higher than needed.
- Energy Charges (EC): the cost of the units (kWh) you actually used, units × rate
  per unit. Using less electricity lowers it.
- FPPCA / FAC / FPPPA (Fuel and Power Purchase Cost Adjustment): an extra per-unit
  charge when the cost of fuel and buying power goes up after tariffs were set.
  It changes month to month and is approved by the state regulator.
- P & G Surcharge (Pension & Gratuity surcharge): a per-unit charge, approved by
  the regulator (KERC in Karnataka), to fund pension and gratuity of electricity
  company employees. "GOK portion" means the part linked to the Government of
  Karnataka's share.
- Tax @ 9% (Electricity Tax / Electricity Duty): a tax charged by the state
  government on electricity consumption, as a percentage of the charges.
- True-up Charges: a recovery of the gap between the costs the electricity company
  expected and its actual costs in earlier years, approved by the regulator and
  added per unit for a limited period.
  - True-up Charges (EC): the true-up amount on your energy charges.
  - True-up Charges (Tax): the electricity tax on that true-up amount.
  - True-up Charges (GJ Sub): the Gruha Jyothi subsidy covering the true-up amount
    (shown as a deduction when the government pays it for you).
  - True-up Charges (GJ Tax): the Gruha Jyothi subsidy covering the tax on the
    true-up amount.
- Gruha Jyothi (GJ): Karnataka government scheme giving free electricity to homes
  up to an eligible monthly limit of units (based on past average usage + 10%).
  If you use more than your limit, you pay for the extra units.
- Rebate: a discount, e.g. for prompt or digital payment or a solar water heater.
- Interest / DPC (Delayed Payment Charges): charged when a previous bill was paid
  late. Paying before the due date avoids it.
- Arrears: unpaid amount from earlier bills (a positive amount), or a credit carried
  forward if shown as negative.
- ASD (Additional Security Deposit): extra deposit asked when your average bill has
  increased, so the deposit covers about two months of bills. It is refundable.
- Sanctioned / Connected Load (kW): the maximum power your connection is approved for.
- Tariff category (e.g. LT-1, LT-2a): the type of connection (home, commercial,
  etc.), which decides the rates.
- MD (Maximum Demand) and PF (Power Factor) penalty: mostly for commercial or
  industrial connections.

WATER (e.g. BWSSB)
- Water Charges: cost of the water used, in kilolitres (1 KL = 1000 litres).
- Sanitary / UGD Charges: for sewage (underground drainage), often a percentage of
  water charges.
- Meter Rent / Meter Cost: a small monthly charge for the water meter.
- Borewell Charges / Cess: a charge on properties that also use a borewell.

MOBILE / BROADBAND / DTH
- Plan / Rental Charges: the fixed monthly cost of your plan.
- Usage Charges: extra charges beyond the plan (data, calls, SMS, roaming).
- GST @ 18% (CGST 9% + SGST 9%, or IGST 18%): goods and services tax on the bill.
- Late Payment Fee: charged when the previous bill was paid after the due date.
- One-time / Installation Charges: charged once for a new connection or device.
"""

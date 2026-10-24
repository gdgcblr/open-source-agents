"""Generate SYNTHETIC sample documents for demos and tests.

Every person, number and address here is invented. Identifiers carry valid checksums so the
detectors are exercised realistically, and every document is stamped SPECIMEN.

Run: uv run python scripts/make_samples.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from aran.detectors import gstin_check_char, verhoeff_check_digit

OUT = Path(__file__).resolve().parent.parent / "samples"


def aadhaar(base11: str) -> str:
    d = base11 + verhoeff_check_digit(base11)
    return f"{d[:4]} {d[4:8]} {d[8:]}"


APPLICANT = {
    "name": "Karthik Ramanathan",
    "father": "Ramanathan Subramanian",
    "dob": "14/03/1991",
    "gender": "Male",
    "aadhaar": aadhaar("48215730962"),
    "pan": "BQKPR4821M",
    "phone": "+91 90000 41275",
    "email": "karthik.r@example.com",
    "upi": "karthik.r@okexample",
    "address": "No. 12, 4th Cross, Indiranagar 2nd Stage, Bengaluru, Karnataka",
    "pin": "560038",
    "account": "50100234567812",
    "ifsc": "HDFC0001234",
    "employer": "Nimbus Analytics Pvt Ltd",
    "employer_gstin": "29AAKCN7712Q1Z" + gstin_check_char("29AAKCN7712Q1Z"),
}


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _stamp(draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
    draw.text((w - 230, h - 50), "SPECIMEN", fill=(200, 30, 30), font=_font(34))


def aadhaar_card(path: Path) -> None:
    a = APPLICANT
    img = Image.new("RGB", (900, 560), (252, 250, 245))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 70], fill=(255, 153, 51))
    d.text((30, 18), "Government of India  (SAMPLE - NOT A REAL DOCUMENT)", fill="black", font=_font(28))
    d.rectangle([30, 100, 230, 340], outline=(120, 120, 120), width=3)
    d.text((80, 205), "PHOTO", fill=(150, 150, 150), font=_font(28))
    street, _, city = a["address"].partition(", Indiranagar")
    y = 105
    for line in (a["name"], f"DOB: {a['dob']}", a["gender"], f"Address: {street},",
                 f"Indiranagar{city}", f"PIN: {a['pin']}"):
        d.text((260, y), line, fill="black", font=_font(24))
        y += 44
    d.text((200, 425), a["aadhaar"], fill="black", font=_font(48))
    d.rectangle([0, 500, 900, 560], fill=(19, 136, 8))
    _stamp(d, 900, 480)
    img.save(path)


def pan_card(path: Path) -> None:
    a = APPLICANT
    img = Image.new("RGB", (900, 560), (225, 238, 250))
    d = ImageDraw.Draw(img)
    d.text((30, 25), "INCOME TAX DEPARTMENT (SAMPLE - NOT A REAL DOCUMENT)", fill=(20, 40, 120), font=_font(28))
    d.text((30, 110), "Permanent Account Number Card", fill="black", font=_font(26))
    d.text((30, 160), a["pan"], fill="black", font=_font(48))
    rows = [("Name", a["name"]), ("Father's Name", a["father"]), ("Date of Birth", a["dob"])]
    y = 250
    for label, value in rows:
        d.text((30, y), label, fill=(80, 80, 80), font=_font(22))
        d.text((30, y + 28), value, fill="black", font=_font(30))
        y += 85
    _stamp(d, 900, 540)
    img.save(path)


def bank_statement(path: Path) -> None:
    a = APPLICANT
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "SAMPLE BANK - Statement of Account (SPECIMEN, synthetic data)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for line in (
        f"Account Holder: {a['name']}",
        f"Address: {a['address']} - {a['pin']}",
        f"A/c No: {a['account']}    IFSC: {a['ifsc']}    Branch: Indiranagar",
        f"Registered Mobile: {a['phone']}    Email: {a['email']}",
        f"PAN: {a['pan']}    Period: 01/07/2026 to 30/09/2026",
    ):
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    widths = (22, 100, 22, 22, 24)
    for w, h in zip(widths, ("Date", "Narration", "Debit", "Credit", "Balance")):
        pdf.cell(w, 7, h, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    bal = 42350.00
    rows = []
    for month, mm in (("Jul", "07"), ("Aug", "08"), ("Sep", "09")):
        rows += [
            (f"01/{mm}/2026", f"NEFT CR SALARY {a['employer'].upper()} {month.upper()}", 0, 86500),
            (f"03/{mm}/2026", "ACH DR HDFC CAR LOAN EMI LN88213", 14500, 0),
            (f"05/{mm}/2026", "UPI/rent/suresh.babu@okexample/Suresh Babu", 22000, 0),
            (f"09/{mm}/2026", "ATM CASH WDL INDIRANAGAR", 10000, 0),
            (f"18/{mm}/2026", "POS AMAZON PAY INDIA", 6420, 0),
            (f"25/{mm}/2026", "ACH DR BAJAJ FINSERV EMI PL5521", 9800, 0),
        ]
    rows.insert(12, ("26/08/2026", "ACH RETURN BAJAJ FINSERV EMI PL5521 - INSUFFICIENT FUNDS", 0, 9800))
    rows.insert(13, ("26/08/2026", "CHQ/ECS RETURN CHARGES", 590, 0))
    for dt, narration, dr, cr in rows:
        bal += cr - dr
        for w, v in zip(widths, (dt, narration[:62], f"{dr:,.2f}" if dr else "", f"{cr:,.2f}" if cr else "", f"{bal:,.2f}")):
            pdf.cell(w, 6, v, border=1)
        pdf.ln()
    pdf.ln(4)
    pdf.set_text_color(200, 30, 30)
    pdf.cell(0, 6, "SPECIMEN - generated test data, not a real customer.", new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def salary_slip(path: Path) -> None:
    a = APPLICANT
    path.write_text(
        f"""{a['employer']} - Payslip for September 2026 (SPECIMEN, synthetic data)
GSTIN: {a['employer_gstin']}
Employee Name: {a['name']}
Employee ID: NA-20417        Designation: Senior Data Engineer
PAN: {a['pan']}              Bank A/c No: {a['account']} ({a['ifsc']})
Date of Birth: {a['dob']}    Date of Joining: 02/05/2022

Earnings                      Deductions
Basic          45,000         Provident Fund   5,400
HRA            22,500         Professional Tax   200
Special Allow. 30,800         Income Tax (TDS) 6,200
Gross          98,300         Total Deductions 11,800

Net Pay: 86,500
"""
    )


def lab_report(path: Path) -> None:
    img = Image.new("RGB", (900, 1000), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 25), "KAVERI DIAGNOSTICS (SAMPLE LAB - SPECIMEN)", fill=(10, 80, 120), font=_font(30))
    d.text((30, 65), "Jayanagar, Bengaluru | Ph: 080 4000 1234", fill=(90, 90, 90), font=_font(20))
    lines = [
        "Patient Name: Meenakshi Sundaram",
        "UHID: KDC-88231        Date of Birth: 22/07/1968",
        "Mobile: +91 90000 73314   Sample Date: 10/10/2026",
        "Referred By: Dr. Priya Venkatesh",
        "Address: 7, Temple Street, Basavanagudi, Bengaluru",
        "",
        "TEST                     RESULT     REF. RANGE",
        "HbA1c                    8.2 %  H   4.0 - 5.6",
        "Fasting Glucose          168 mg/dL H 70 - 100",
        "Total Cholesterol        232 mg/dL H < 200",
        "LDL Cholesterol          151 mg/dL H < 100",
        "Serum Creatinine         1.0 mg/dL  0.6 - 1.1",
        "TSH                      2.4 uIU/mL 0.4 - 4.0",
    ]
    y = 130
    for line in lines:
        d.text((30, y), line, fill="black", font=_font(26))
        y += 46
    _stamp(d, 900, 960)
    img.save(path)


def customers_csv(path: Path) -> None:
    rows = [
        ("customer_name", "mobile", "email", "pan", "aadhaar", "city", "loan_amount", "bank_name"),
        ("Karthik Ramanathan", "+91 90000 41275", "karthik.r@example.com", "BQKPR4821M", APPLICANT["aadhaar"], "Bengaluru", "1200000", "HDFC Bank"),
        ("Divya Natarajan", "+91 90000 58210", "divya.n@example.com", "CXNPN7310K", aadhaar("62738190451"), "Chennai", "450000", "ICICI Bank"),
        ("Arjun Mehta", "+91 90000 22984", "arjun.m@example.com", "DLMPM2209Q", aadhaar("39017264583"), "Pune", "800000", "Axis Bank"),
        ("Fathima Begum", "+91 90000 66127", "fathima.b@example.com", "EFRPB5512H", aadhaar("75310428619"), "Hyderabad", "300000", "SBI"),
    ]
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)


def main() -> None:
    (OUT / "kyc").mkdir(parents=True, exist_ok=True)
    (OUT / "health").mkdir(parents=True, exist_ok=True)
    aadhaar_card(OUT / "kyc" / "aadhaar_card.png")
    pan_card(OUT / "kyc" / "pan_card.png")
    bank_statement(OUT / "kyc" / "bank_statement.pdf")
    salary_slip(OUT / "kyc" / "salary_slip.txt")
    customers_csv(OUT / "customers.csv")
    lab_report(OUT / "health" / "lab_report.png")
    # Ground truth for agent evals. Kept OUTSIDE samples/kyc so an agent can never read it.
    truth = {k: APPLICANT[k] for k in ("name", "father", "dob", "aadhaar", "pan", "phone", "email",
                                        "upi", "address", "pin", "account", "employer_gstin")}
    truth["expected"] = {"verdict": "REFER", "net_monthly_salary": 86500,
                         "monthly_emis": [14500, 9800], "bounces": 1}
    (OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    for p in sorted(OUT.rglob("*.*")):
        print(p.relative_to(OUT.parent))


if __name__ == "__main__":
    main()

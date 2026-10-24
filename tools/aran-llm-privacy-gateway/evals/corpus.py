"""Deterministic, labelled, SYNTHETIC evaluation corpus.

Every case lists the personal values that must NOT survive redaction (`pii`) and the useful
values that MUST survive it (`keep`). All names and numbers are generated; identifiers carry
valid checksums so they look real to the detectors but belong to no one.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from aran.detectors import gstin_check_char, luhn_valid, verhoeff_check_digit

FIRST = ["Karthik", "Divya", "Arjun", "Fathima", "Priya", "Rahul", "Lakshmi", "Mohammed", "Ananya",
         "Venkatesh", "Sneha", "Harpreet", "Joseph", "Meera", "Suresh", "Aisha", "Rohan", "Kavya",
         "Imran", "Deepa", "Gurpreet", "Nandini", "Sanjay", "Revathi"]
LAST = ["Ramanathan", "Natarajan", "Mehta", "Begum", "Sharma", "Iyer", "Reddy", "Singh", "Khan",
        "Nair", "Patel", "Das", "Menon", "Gupta", "Fernandes", "Chatterjee", "Kulkarni", "Pillai"]
STREETS = ["4th Cross, Indiranagar", "MG Road, Ashok Nagar", "Temple Street, Basavanagudi",
           "Anna Salai, Teynampet", "Linking Road, Bandra West", "Park Street, Taltala"]
CITIES = ["Bengaluru", "Chennai", "Mumbai", "Kolkata", "Hyderabad", "Pune"]
EMPLOYERS = ["Nimbus Analytics Pvt Ltd", "Tata Consultancy Services", "Infosys Limited", "Zoho Corporation"]
BANKS_IFSC = ["HDFC0001234", "ICIC0004521", "SBIN0007788", "UTIB0000123"]
UPI_HANDLES = ["okaxis", "okicici", "oksbi", "ybl"]


@dataclass
class Case:
    id: str
    template: str
    profile: str
    text: str
    pii: list[tuple[str, str]] = field(default_factory=list)   # (type, value) must be hidden
    keep: list[str] = field(default_factory=list)              # values that must remain


class Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)

    def digits(self, n: int) -> str:
        return "".join(self.r.choice("0123456789") for _ in range(n))

    def name(self) -> str:
        return f"{self.r.choice(FIRST)} {self.r.choice(LAST)}"

    def aadhaar(self) -> str:
        base = self.r.choice("23456789") + self.digits(10)
        d = base + verhoeff_check_digit(base)
        return self.r.choice([f"{d[:4]} {d[4:8]} {d[8:]}", d, f"{d[:4]}-{d[4:8]}-{d[8:]}"])

    def bad_aadhaar(self) -> str:
        """12 digits that fail Verhoeff: a reference number, not an Aadhaar."""
        base = self.r.choice("23456789") + self.digits(10)
        good = int(verhoeff_check_digit(base))
        return base + str((good + 1 + self.r.randrange(9)) % 10)

    def pan(self, surname: str, holder: str = "P") -> str:
        L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return "".join(self.r.choice(L) for _ in range(3)) + holder + surname[0].upper() + self.digits(4) + self.r.choice(L)

    def gstin(self) -> str:
        first14 = self.r.choice(["29", "33", "27", "07"]) + self.pan("Corp", "C") + "1Z"
        return first14 + gstin_check_char(first14)

    def phone(self) -> str:
        n = self.r.choice("6789") + self.digits(9)
        return self.r.choice([f"+91 {n[:5]} {n[5:]}", n, f"+91-{n}", f"0{n}"])

    def card(self) -> str:
        while True:
            d = "4" + self.digits(15)
            if luhn_valid(d):
                return " ".join(d[i:i + 4] for i in range(0, 16, 4))

    def account(self) -> str:
        return self.digits(self.r.choice([11, 12, 14, 16]))

    def dob(self) -> str:
        return f"{self.r.randint(1, 28):02d}/{self.r.randint(1, 12):02d}/{self.r.randint(1960, 2002)}"

    def address(self) -> str:
        return f"No. {self.r.randint(1, 99)}, {self.r.choice(STREETS)}, {self.r.choice(CITIES)}"

    def pin(self) -> str:
        return self.r.choice("12345678") + self.digits(5)

    def amount(self) -> str:
        return f"{self.r.randint(10, 250) * 500:,}"

    def txn_date(self) -> str:
        return f"{self.r.randint(1, 28):02d}/{self.r.randint(7, 9):02d}/2026"


def _kyc_form(g: Gen, i: int) -> Case:
    name, father = g.name(), g.name()
    aad, pan, ph = g.aadhaar(), g.pan(name.split()[1]), g.phone()
    dob, addr, pin, acct = g.dob(), g.address(), g.pin(), g.account()
    ifsc, emp, sal = g.r.choice(BANKS_IFSC), g.r.choice(EMPLOYERS), g.amount()
    text = (f"LOAN APPLICATION FORM\nApplicant Name: {name}\nFather's Name: {father}\n"
            f"Date of Birth: {dob}\nPAN: {pan}\nAadhaar: {aad}\nMobile: {ph}\n"
            f"Address: {addr}\nPIN: {pin}\nEmployer: {emp}\nNet monthly salary: Rs {sal}\n"
            f"Salary A/c No: {acct}  IFSC: {ifsc}\n")
    pii = [("PERSON", name), ("PERSON", father), ("DOB", dob), ("PAN", pan), ("AADHAAR", aad),
           ("PHONE", ph), ("ADDRESS", addr), ("PINCODE", pin), ("ACCOUNT_NUMBER", acct)]
    return Case(f"kyc_form_{i}", "kyc_form", "kyc", text, pii, [ifsc, sal, emp])


def _loan_email(g: Gen, i: int) -> Case:
    name = g.name()
    pan, ph, acct = g.pan(name.split()[1]), g.phone(), g.account()
    email = f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.com"
    ifsc, amt, ref = g.r.choice(BANKS_IFSC), g.amount(), g.bad_aadhaar()
    text = (f"Hi team,\nPlease process the home loan for {name} (PAN {pan}). "
            f"They can be reached at {ph} or {email}. Salary of Rs {amt} is credited to "
            f"account number {acct} at IFSC {ifsc}. Our internal reference is {ref}.\nThanks")
    pii = [("PERSON", name), ("PAN", pan), ("PHONE", ph), ("EMAIL", email), ("ACCOUNT_NUMBER", acct)]
    return Case(f"loan_email_{i}", "loan_email", "kyc", text, pii, [ifsc, amt, ref])


def _bank_lines(g: Gen, i: int) -> Case:
    payee = g.name()
    upi = f"{payee.split()[0].lower()}.{payee.split()[1][0].lower()}@{g.r.choice(UPI_HANDLES)}"
    lines, keep = [], []
    for _ in range(4):
        d, a = g.txn_date(), g.amount()
        lines.append(f"{d} UPI/{upi}/{payee} DR {a}")
        keep += [d, a]
    emi = g.amount()
    lines.append(f"{g.txn_date()} ACH DR BAJAJ FINSERV EMI PL{g.digits(4)} {emi}")
    keep.append(emi)
    return Case(f"bank_lines_{i}", "bank_lines", "kyc", "\n".join(lines),
                [("UPI", upi), ("PERSON", payee)], keep)


def _support_chat(g: Gen, i: int) -> Case:
    name = g.name()
    aad, card, ph = g.aadhaar(), g.card(), g.phone()
    text = (f"Customer: hello, this is {name}. my card {card} got blocked after KYC update.\n"
            f"Customer: my aadhaar is {aad} and registered number {ph}\n"
            "Agent: Thanks, raising a ticket for the card block.")
    return Case(f"support_chat_{i}", "support_chat", "kyc", text,
                [("PERSON", name), ("CARD", card), ("AADHAAR", aad), ("PHONE", ph)], ["KYC update"])


def _gst_invoice(g: Gen, i: int) -> Case:
    cust = g.name()
    gstin, amt, inv = g.gstin(), g.amount(), f"INV-2026-{g.digits(4)}"
    text = (f"TAX INVOICE {inv}\nSupplier GSTIN: {gstin}\nCustomer Name: {cust}\n"
            f"Taxable value: Rs {amt}\nIGST 18%\n")
    return Case(f"gst_invoice_{i}", "gst_invoice", "kyc", text,
                [("GSTIN", gstin), ("PERSON", cust)], [inv, amt])


def _lab_report(g: Gen, i: int) -> Case:
    patient, doctor = g.name(), g.name()
    uhid, dob, ph, addr = f"KDC-{g.digits(5)}", g.dob(), g.phone(), g.address()
    hba1c = f"{g.r.randint(50, 110) / 10:.1f}"
    text = (f"KAVERI DIAGNOSTICS\nPatient Name: {patient}\nUHID: {uhid}   Date of Birth: {dob}\n"
            f"Mobile: {ph}\nReferred By: Dr. {doctor}\nAddress: {addr}\n\nHbA1c {hba1c} %   4.0 - 5.6\n"
            "Fasting Glucose 168 mg/dL  70 - 100\n")
    pii = [("PERSON", patient), ("PERSON", doctor), ("MEDICAL_ID", uhid), ("DOB", dob),
           ("PHONE", ph), ("ADDRESS", addr)]
    return Case(f"lab_report_{i}", "lab_report", "health", text, pii, [hba1c, "Fasting Glucose 168"])


TEMPLATES = [_kyc_form, _loan_email, _bank_lines, _support_chat, _gst_invoice, _lab_report]


def build(n_per_template: int = 30, seed: int = 7) -> list[Case]:
    g = Gen(seed)
    return [t(g, i) for t in TEMPLATES for i in range(n_per_template)]


def ocr_noise(g: Gen, value: str) -> str:
    """Simulate a typical OCR error: drop or substitute one character."""
    i = g.r.randrange(len(value))
    if g.r.random() < 0.5:
        return value[:i] + value[i + 1:]
    swap = {"0": "O", "1": "I", "5": "S", "8": "B", "O": "0", "I": "1", "S": "5", "B": "8"}
    return value[:i] + swap.get(value[i], "7" if value[i].isdigit() else "X") + value[i + 1:]


def build_ocr_suite(n: int = 60, seed: int = 11) -> list[Case]:
    """ID cards whose number was misread by OCR: must still be hidden in scan mode."""
    g = Gen(seed)
    cases = []
    for i in range(n):
        name = g.name()
        if i % 2:
            noisy = ocr_noise(g, g.pan(name.split()[1]))
            text = f"INCOME TAX DEPARTMENT\nPermanent Account Number Card\n{noisy}\nName\n{name}\n"
        else:
            noisy = ocr_noise(g, g.aadhaar().replace(" ", "").replace("-", ""))
            text = f"Government of India\n{name}\nAadhaar\n{noisy[:4]} {noisy[4:8]} {noisy[8:]}\n"
            noisy = f"{noisy[:4]} {noisy[4:8]} {noisy[8:]}"
        cases.append(Case(f"ocr_{i}", "ocr_noise", "kyc", text, [("ID_NUMBER", noisy)], []))
    return cases

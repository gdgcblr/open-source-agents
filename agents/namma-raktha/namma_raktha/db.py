"""
SQLite Database Layer for NammaRaktha.
Zero-dependency, persistent storage for voluntary donor registry and emergency logs.
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import BloodGroup, BangaloreZone, DonorRecord

DB_PATH = Path(__file__).resolve().parent.parent / "namma_raktha.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes SQLite schema and seeds realistic Bengaluru voluntary donors."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS donors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        blood_group TEXT NOT NULL,
        zone TEXT NOT NULL,
        area TEXT NOT NULL,
        can_donate_sdp INTEGER DEFAULT 0,
        is_available INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emergency_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT DEFAULT 'Emergency Patient',
        blood_group TEXT NOT NULL,
        component TEXT NOT NULL,
        units INTEGER DEFAULT 1,
        hospital_name TEXT NOT NULL,
        hospital_address TEXT DEFAULT '',
        zone TEXT NOT NULL,
        urgency TEXT NOT NULL,
        contact_name TEXT DEFAULT 'Attendant',
        contact_phone TEXT NOT NULL,
        status TEXT DEFAULT 'OPEN',
        accepted_by TEXT DEFAULT NULL,
        accepted_phone TEXT DEFAULT NULL,
        accepted_at TIMESTAMP DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Migration: Ensure columns exist if table was previously created with older schema
    cursor.execute("PRAGMA table_info(emergency_logs);")
    existing_cols = [row[1] for row in cursor.fetchall()]
    needed_cols = [
        ("patient_name", "TEXT DEFAULT 'Emergency Patient'"),
        ("hospital_address", "TEXT DEFAULT ''"),
        ("contact_name", "TEXT DEFAULT 'Attendant'"),
        ("status", "TEXT DEFAULT 'OPEN'"),
        ("accepted_by", "TEXT DEFAULT NULL"),
        ("accepted_phone", "TEXT DEFAULT NULL"),
        ("accepted_at", "TIMESTAMP DEFAULT NULL")
    ]
    for col_name, col_def in needed_cols:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE emergency_logs ADD COLUMN {col_name} {col_def};")
            except Exception:
                pass

    # Seed initial Bengaluru volunteer community if table is empty
    cursor.execute("SELECT COUNT(*) FROM donors;")
    count = cursor.fetchone()[0]

    if count == 0:
        seed_donors = [
            ("Karthik Rajan", "+91 98860 44321", BloodGroup.A_POS.value, BangaloreZone.EAST.value, "Indiranagar 100ft Rd", 1),
            ("Deepa Nair", "+91 97410 88234", BloodGroup.O_NEG.value, BangaloreZone.SOUTH.value, "Jayanagar 4th Block", 0),
            ("Rahul Sharma", "+91 99001 55678", BloodGroup.B_POS.value, BangaloreZone.EAST.value, "Whitefield ITPL", 1),
            ("Sneha Kulkarni", "+91 98450 33412", BloodGroup.O_POS.value, BangaloreZone.SOUTH.value, "HSR Layout Sector 1", 1),
            ("Aniruddha Hegde", "+91 96111 22890", BloodGroup.AB_POS.value, BangaloreZone.WEST.value, "Malleshwaram 8th Cross", 0),
            ("Vignesh Gowda", "+91 97312 66543", BloodGroup.A_NEG.value, BangaloreZone.NORTH.value, "Hebbal Kempapura", 1),
            ("Dr. Vikram Rao", "+91 98440 99876", BloodGroup.BOMBAY.value, BangaloreZone.CENTRAL.value, "Richmond Town", 0),
            ("Pooja Iyer", "+91 98800 11224", BloodGroup.A_POS.value, BangaloreZone.SOUTH.value, "Koramangala 5th Block", 1),
            ("Manjunath B.", "+91 99450 77881", BloodGroup.O_NEG.value, BangaloreZone.CENTRAL.value, "Majestic / Gandhinagar", 0),
            ("Arjun Mehta", "+91 98455 12345", BloodGroup.B_POS.value, BangaloreZone.SOUTH.value, "BTM Layout 2nd Stage", 1),
        ]

        cursor.executemany("""
            INSERT INTO donors (name, phone, blood_group, zone, area, can_donate_sdp)
            VALUES (?, ?, ?, ?, ?, ?);
        """, seed_donors)
        conn.commit()

    # Seed initial realistic Bengaluru open emergency requests if empty
    cursor.execute("SELECT COUNT(*) FROM emergency_logs;")
    emergencies_count = cursor.fetchone()[0]

    if emergencies_count == 0:
        seed_emergencies = [
            ("Ananya M. (IP: 5542)", "A+", "Platelets (SDP - Single Donor Apheresis)", 2, "Manipal Hospital", "HAL Old Airport Road, Kodihalli", BangaloreZone.EAST.value, "CRITICAL (<2 Hours - ICU/Emergency)", "Suresh", "+91 98860 12345", "OPEN"),
            ("Rameshwar (Trauma)", "O-", "Whole Blood", 2, "Victoria Hospital (BMCRI)", "Fort Road, Near KR Market", BangaloreZone.CENTRAL.value, "URGENT (2-6 Hours)", "Dr. Ramesh", "+91 98450 11223", "OPEN"),
            ("Master Chetan", "B+", "Platelets (SDP - Single Donor Apheresis)", 1, "Kidwai Memorial Institute of Oncology", "Dr MH Marigowda Rd, Hombegowda Nagar", BangaloreZone.SOUTH.value, "URGENT (2-6 Hours)", "Anitha", "+91 99001 12233", "OPEN"),
            ("Emergency ICU", "Bombay (hh)", "PRBC (Packed Red Blood Cells)", 2, "Sri Jayadeva Institute of Cardiovascular Sciences", "Bannerghatta Main Road, 9th Block Jayanagar", BangaloreZone.SOUTH.value, "CRITICAL (<2 Hours - ICU/Emergency)", "Attendant", "+91 97410 98765", "OPEN"),
        ]
        cursor.executemany("""
            INSERT INTO emergency_logs 
            (patient_name, blood_group, component, units, hospital_name, hospital_address, zone, urgency, contact_name, contact_phone, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, seed_emergencies)
        conn.commit()

    conn.close()


def add_donor(name: str, phone: str, blood_group: str, zone: str, area: str, can_donate_sdp: bool = False) -> int:
    """Registers a new voluntary donor into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO donors (name, phone, blood_group, zone, area, can_donate_sdp)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (name, phone, blood_group, zone, area, 1 if can_donate_sdp else 0))
    donor_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return donor_id


def find_matching_donors(
    compatible_groups: List[BloodGroup],
    patient_zone: BangaloreZone,
    needs_sdp: bool = False,
    limit: int = 4
) -> List[DonorRecord]:
    """
    Finds voluntary donors matching compatible blood groups,
    prioritized by donors residing in the exact same Bengaluru zone (traffic-friendly).
    """
    conn = get_connection()
    cursor = conn.cursor()

    group_values = [g.value for g in compatible_groups]
    placeholders = ",".join("?" for _ in group_values)

    query = f"""
        SELECT id, name, phone, blood_group, zone, area, can_donate_sdp, is_available
        FROM donors
        WHERE is_available = 1
          AND blood_group IN ({placeholders})
    """
    params = list(group_values)

    if needs_sdp:
        query += " AND can_donate_sdp = 1"

    # Prioritize donors in the same Bengaluru zone first to beat traffic!
    query += " ORDER BY CASE WHEN zone = ? THEN 0 ELSE 1 END, id ASC LIMIT ?"
    params.append(patient_zone.value)
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    donors = []
    for r in rows:
        try:
            bg = BloodGroup(r["blood_group"])
            zone = BangaloreZone(r["zone"])
        except ValueError:
            bg = BloodGroup.O_POS
            zone = BangaloreZone.CENTRAL

        donors.append(DonorRecord(
            id=r["id"],
            name=r["name"],
            phone=r["phone"],
            blood_group=bg,
            zone=zone,
            area=r["area"],
            can_donate_sdp=bool(r["can_donate_sdp"]),
            is_available=bool(r["is_available"])
        ))

    return donors


def log_emergency(req) -> int:
    """Logs an emergency triage request for clinical tracking and dashboard feed."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO emergency_logs (
            patient_name, blood_group, component, units, hospital_name,
            hospital_address, zone, urgency, contact_name, contact_phone, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN');
    """, (
        getattr(req, "patient_name", None) or "Emergency Patient",
        req.blood_group.value,
        req.component.value,
        req.units,
        req.hospital_name,
        getattr(req, "hospital_address", "") or "",
        req.zone.value,
        req.urgency.value,
        getattr(req, "contact_name", "Attendant") or "Attendant",
        req.contact_phone
    ))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_recent_emergencies(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieves recent emergency requisitions for the live dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            id, patient_name, blood_group, component, units, hospital_name,
            hospital_address, zone, urgency, contact_name, contact_phone,
            status, accepted_by, accepted_phone, accepted_at, created_at
        FROM emergency_logs
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    emergencies = []
    for r in rows:
        emergencies.append({
            "id": r["id"],
            "patient_name": r["patient_name"],
            "blood_group": r["blood_group"],
            "component": r["component"],
            "units": r["units"],
            "hospital_name": r["hospital_name"],
            "hospital_address": r["hospital_address"] or "",
            "zone": r["zone"],
            "urgency": r["urgency"],
            "contact_name": r["contact_name"] or "Attendant",
            "contact_phone": r["contact_phone"],
            "status": r["status"] or "OPEN",
            "accepted_by": r["accepted_by"],
            "accepted_phone": r["accepted_phone"],
            "accepted_at": r["accepted_at"],
            "created_at": r["created_at"]
        })
    return emergencies


def accept_emergency(request_id: int, donor_name: str, donor_phone: str) -> bool:
    """Marks an emergency requisition as accepted by a voluntary donor."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE emergency_logs
        SET status = 'ACCEPTED',
            accepted_by = ?,
            accepted_phone = ?,
            accepted_at = CURRENT_TIMESTAMP
        WHERE id = ?;
    """, (donor_name, donor_phone, request_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0


def get_all_donors_count() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM donors;")
    count = cursor.fetchone()[0]
    conn.close()
    return count


# Auto-initialize database schema on module load
init_db()

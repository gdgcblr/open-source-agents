"""
Data models and enumerations for NammaRaktha.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class BloodGroup(str, Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    BOMBAY = "Bombay (hh)"


class BloodComponent(str, Enum):
    WHOLE_BLOOD = "Whole Blood"
    PLATELETS_SDP = "Platelets (SDP - Single Donor Apheresis)"
    PLATELETS_RDP = "Platelets (RDP - Random Donor)"
    PACKED_RED_CELLS = "PRBC (Packed Red Blood Cells)"
    FRESH_FROZEN_PLASMA = "FFP (Fresh Frozen Plasma)"
    CRYOPRECIPITATE = "Cryoprecipitate"


class UrgencyLevel(str, Enum):
    CRITICAL = "CRITICAL (<2 Hours - ICU/Emergency)"
    URGENT = "URGENT (2-6 Hours)"
    STANDARD = "STANDARD (Within 24 Hours)"
    PLANNED = "PLANNED (Scheduled Surgery)"


class BangaloreZone(str, Enum):
    CENTRAL = "Central Bengaluru (Majestic, MG Road, Shivaji Nagar, Market)"
    EAST = "East Bengaluru (Indiranagar, Whitefield, Marathahalli, HAL)"
    SOUTH = "South Bengaluru (Jayanagar, BTM, HSR, Koramangala, Bannerghatta, E-City)"
    NORTH = "North Bengaluru (Hebbal, Yelahanka, Manyata, Mathikere)"
    WEST = "West Bengaluru (Malleshwaram, Rajajinagar, Vijayanagar, Kengeri)"


class PatientRequirement(BaseModel):
    patient_name: Optional[str] = Field(default=None, description="Patient name or pseudonym")
    blood_group: BloodGroup = Field(description="Required blood group")
    component: BloodComponent = Field(default=BloodComponent.WHOLE_BLOOD, description="Specific blood component")
    units: int = Field(default=1, ge=1, le=10, description="Units or bags needed")
    hospital_name: str = Field(description="Name of hospital or nursing home")
    hospital_address: str = Field(default="", description="Street, landmark, or area")
    zone: BangaloreZone = Field(default=BangaloreZone.CENTRAL, description="Bengaluru geographic zone")
    urgency: UrgencyLevel = Field(default=UrgencyLevel.URGENT, description="Emergency urgency level")
    contact_name: str = Field(default="Attendant", description="Name of contact person")
    contact_phone: str = Field(description="Phone number for verification and donor coordination")
    case_or_ip_number: Optional[str] = Field(default=None, description="Hospital IP / Ward / Case Number")
    diagnosis_or_notes: Optional[str] = Field(default=None, description="e.g. Dengue, cardiac surgery, accident trauma")


class CompatibilityResult(BaseModel):
    recipient_group: BloodGroup
    component: BloodComponent
    compatible_donor_groups: List[BloodGroup]
    ideal_donor_group: BloodGroup
    universal_donor_for_type: str
    clinical_notes: List[str]
    donor_eligibility_criteria: List[str]


class BloodBank(BaseModel):
    name: str
    zone: BangaloreZone
    area: str
    address: str
    phone: str
    is_24x7: bool = True
    has_apheresis: bool = True
    google_maps_query: str
    metro_proximity: str
    peak_traffic_advisory: str


class SOSMessage(BaseModel):
    english_text: str
    kannada_text: str
    kannada_phonetic: str
    whatsapp_share_url: str
    twitter_share_url: str
    twitter_text: str
    donor_accept_url: str = Field(default="")
    hospital_maps_url: str = Field(default="")
    verification_checklist: List[str]
    whatsapp_cloud_api_payload: Optional[dict] = Field(default=None)


class DonorRecord(BaseModel):
    id: Optional[int] = None
    name: str
    phone: str
    blood_group: BloodGroup
    zone: BangaloreZone
    area: str
    can_donate_sdp: bool = False
    is_available: bool = True


class ValidationWarning(BaseModel):
    field: str
    severity: str  # 'critical', 'warning', 'info'
    message: str
    action_needed: str


class GuardrailCheckResult(BaseModel):
    is_safe: bool = True
    violation_reason: Optional[str] = None
    is_commercial_scam: bool = False
    is_off_topic: bool = False


class AgentTriageResult(BaseModel):
    requirement: PatientRequirement
    compatibility: CompatibilityResult
    matched_blood_banks: List[BloodBank]
    matched_donors: List[DonorRecord] = Field(default_factory=list)
    sos: SOSMessage
    actionable_advice: str
    validation_warnings: List[ValidationWarning] = Field(default_factory=list)
    is_guardrail_blocked: bool = False
    guardrail_message: Optional[str] = None

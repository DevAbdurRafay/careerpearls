from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class UserContract:
    id: int
    name: str
    email: str
    role: str
    is_active: bool = True
    approval_status: str = 'approved'
    oauth_provider: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrganizationContract:
    id: int
    name: str
    domain: Optional[str] = None
    official_email: Optional[str] = None
    ntn_id: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    verification_status: str = 'Pending Verification'
    is_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JobContract:
    id: int
    company_id: int
    company_name: str
    title: str
    category_name: str
    description: str
    location: str
    salary_range: Optional[str] = None
    employment_type: Optional[str] = None
    status: str = 'active'
    created_at: Optional[str] = None
    closes_at: Optional[str] = None
    is_open: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicationContract:
    id: int
    job_id: int
    job_title: str
    company_name: str
    candidate_id: int
    candidate_name: str
    status: str  # Strictly 'Under Review', 'Contacted', or 'Rejected'
    applied_at: str
    cover_letter: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MessageContract:
    id: int
    sender_id: int
    sender_name: str
    receiver_id: int
    receiver_name: str
    application_id: Optional[int] = None
    body: str = ''
    sent_at: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LocationVerificationContract:
    candidate_id: int
    candidate_name: str
    location: str
    is_location_verified: bool
    verified_at: Optional[str] = None
    verified_by_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

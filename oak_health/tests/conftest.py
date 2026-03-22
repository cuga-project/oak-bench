"""
Pytest configuration and shared fixtures for Oak Health Insurance API tests.
"""

import pytest
from fastapi.testclient import TestClient

from oak_health.main import app


@pytest.fixture(scope="session")
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def john_member_id():
    """Member ID for primary test user (JOHN DOE)."""
    return "121231234"


@pytest.fixture
def john_hc_id():
    """Healthcare ID for primary test user (JOHN DOE)."""
    return "868Y10397"


@pytest.fixture
def jane_member_id():
    """Member ID for secondary test user (JANE DOE)."""
    return "882771300"


@pytest.fixture
def jane_hc_id():
    """Healthcare ID for secondary test user (JANE DOE)."""
    return "441Z22001"


@pytest.fixture
def sara_member_id():
    """Member ID for dependent (SARA DOE - JOHN's child)."""
    return "121231235"


@pytest.fixture
def tom_member_id():
    """Member ID for dependent (TOM DOE - JOHN's child)."""
    return "121231236"


@pytest.fixture
def john_coverage_key_2025():
    """Active coverage key for JOHN (2025)."""
    return "1J1U-20250101-20251231-MED-57AMFC"


@pytest.fixture
def john_coverage_key_2024():
    """Inactive coverage key for JOHN (2024)."""
    return "1J1U-20240101-20241231-MED-OLDPPO"


@pytest.fixture
def jane_coverage_key_2025():
    """Active coverage key for JANE (2025)."""
    return "9Z9X-20250101-20251231-MED-INDHMO"


@pytest.fixture
def john_contract_uid():
    """Contract UID for JOHN."""
    return "CONTRACT-UID-JOHN-1001"


@pytest.fixture
def jane_contract_uid():
    """Contract UID for JANE."""
    return "CONTRACT-UID-JANE-2002"


@pytest.fixture
def john_location():
    """Location data for JOHN (Brooklyn, NY). stateCode is the US state abbreviation."""
    return {"stateCode": "NY", "zipCode": "11211"}


@pytest.fixture
def approved_claim_uid():
    """UID for an approved claim."""
    return "451F6F37F295390506B9CF9F6DFBC930"


@pytest.fixture
def denied_claim_uid():
    """UID for a denied claim."""
    return "63FA69DB119C2E16E21B487BC411E1F2"


@pytest.fixture
def pending_claim_uid():
    """UID for a pending claim."""
    return "B1E7C2D8A9F048B7B2A9DCE431F0CD10"


@pytest.fixture
def processing_claim_uid():
    """UID for a processing claim."""
    return "9C0C8D7A6B5A4899BC12EF3344CDA123"


@pytest.fixture
def sara_approved_claim_uid():
    """UID for SARA's approved claim."""
    return "9CUY8Q1A6B28A2ABA3KI333AQW1DA557"


@pytest.fixture
def sara_pending_claim_uid():
    """UID for SARA's pending claim."""
    return "9C0C8D7A6B5A499BA3A4F33AQW1DA211"


@pytest.fixture
def basic_request_body(john_member_id):
    """Basic request body with member ID."""
    return {"memberId": john_member_id}


@pytest.fixture
def request_with_location(john_member_id):
    """Request body with member ID. Location is passed as query params (stateCode/zipCode), not in body."""
    return {"memberId": john_member_id}


@pytest.fixture
def john_location_params(john_location):
    """Location as query params dict for find_care endpoints."""
    return {
        "stateCode": john_location["stateCode"],
        "zipCode": john_location["zipCode"],
    }


# Helper functions
def assert_page_info(metadata, expected_size, expected_page, min_total=0):
    """Assert pagination metadata is correct."""
    page = metadata["page"]
    assert page["size"] == expected_size
    assert page["totalElements"] >= min_total
    assert page["number"] == expected_page
    total_pages = (
        (page["totalElements"] + expected_size - 1) // expected_size
        if expected_size > 0
        else 0
    )
    assert page["totalPages"] == total_pages


def assert_claim_structure(claim):
    """Assert claim has required structure."""
    assert "identifiers" in claim
    assert "uniqueId" in claim["identifiers"]
    assert "displayId" in claim["identifiers"]
    assert "classification" in claim
    assert "status" in claim["classification"]
    assert "parties" in claim
    assert "subject" in claim["parties"]
    assert "financial" in claim
    assert "servicingEntity" in claim["parties"]
    assert "billingEntity" in claim["parties"]

    # Check nested structures
    assert "identifier" in claim["classification"]["status"]
    assert "label" in claim["classification"]["status"]
    assert "details" in claim["classification"]["status"]

    assert "identity" in claim["parties"]["subject"]
    assert "primaryId" in claim["parties"]["subject"]["identity"]
    assert "givenName" in claim["parties"]["subject"]
    assert "familyName" in claim["parties"]["subject"]


def assert_financial_amounts(amount):
    """Assert amount structure has required fields."""
    assert isinstance(amount, dict)
    assert "allocation" in amount or "payment" in amount

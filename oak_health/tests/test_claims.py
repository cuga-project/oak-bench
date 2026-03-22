"""
Tests for Claims-related endpoints:
- POST /get_member_claims
- POST /get_claim_details
- POST /get_claim_eob_pdf
"""

import pytest
from conftest import assert_page_info, assert_claim_structure


class TestGetMemberClaims:
    """Tests for POST /get_member_claims endpoint."""

    def test_basic_claims_retrieval(self, client, basic_request_body):
        """Test Case 1: Basic claims retrieval with default sorting."""
        response = client.post(
            "/get_member_claims",
            json=basic_request_body,
            params={"sort_by": "start_date", "size": 5, "page_index": 0},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "metadata" in data
        assert "claims" in data

        # Check pagination
        assert len(data["claims"]) <= 5
        assert_page_info(data["metadata"], 5, 0, min_total=1)

        # Check claims structure
        for claim in data["claims"]:
            assert_claim_structure(claim)
            assert (
                claim["parties"]["subject"]["identity"]["primaryId"]
                == basic_request_body["memberId"]
            )

    def test_pagination(self, client, basic_request_body):
        """Test Case 2: Pagination works correctly."""
        # Get first page
        response1 = client.post(
            "/get_member_claims",
            json=basic_request_body,
            params={"sort_by": "start_date", "size": 5, "page_index": 0},
        )
        assert response1.status_code == 200
        page1_data = response1.json()
        page1_claims = page1_data["claims"]

        # Get second page
        response2 = client.post(
            "/get_member_claims",
            json=basic_request_body,
            params={"sort_by": "start_date", "size": 5, "page_index": 1},
        )
        assert response2.status_code == 200
        page2_data = response2.json()
        page2_claims = page2_data["claims"]

        # Ensure no duplicates between pages
        page1_uids = {c["identifiers"]["uniqueId"] for c in page1_claims}
        page2_uids = {c["identifiers"]["uniqueId"] for c in page2_claims}
        assert len(page1_uids & page2_uids) == 0, (
            "Pages should not have duplicate claims"
        )

    def test_different_sort_order(self, client, basic_request_body):
        """Test Case 3: Different sort orders work."""
        # Sort by start_date
        response1 = client.post(
            "/get_member_claims",
            json=basic_request_body,
            params={"sort_by": "start_date", "size": 3, "page_index": 0},
        )
        assert response1.status_code == 200
        start_date_claims = response1.json()["claims"]

        # Sort by process_date
        response2 = client.post(
            "/get_member_claims",
            json=basic_request_body,
            params={"sort_by": "process_date", "size": 3, "page_index": 0},
        )
        assert response2.status_code == 200
        process_date_claims = response2.json()["claims"]

        # Should have same claims but potentially different order
        start_uids = [c["identifiers"]["uniqueId"] for c in start_date_claims]
        process_uids = [c["identifiers"]["uniqueId"] for c in process_date_claims]

        # All claims should exist in both (same set)
        assert set(start_uids) == set(process_uids)

    def test_claims_by_hc_id(self, client, john_hc_id):
        """Test Case 4: Can retrieve claims using accountId instead of primaryId."""
        response = client.post(
            "/get_member_claims",
            json={"memberId": john_hc_id},
            params={"sort_by": "start_date", "size": 5, "page_index": 0},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["claims"]) > 0

        # All claims should have matching secondaryId (hcId)
        for claim in data["claims"]:
            assert claim["parties"]["subject"]["identity"]["secondaryId"] == john_hc_id

    def test_missing_member_id(self, client):
        """Test Case 5: Missing memberId returns error."""
        response = client.post(
            "/get_member_claims",
            json={},
            params={"sort_by": "start_date", "size": 5, "page_index": 0},
        )

        assert response.status_code == 422  # Validation error


class TestGetClaimDetails:
    """Tests for POST /get_claim_details endpoint."""

    def test_approved_claim_with_service_lines(
        self, client, basic_request_body, approved_claim_uid
    ):
        """Test Case 1: Approved claim returns service lines and EOBs."""
        response = client.post(
            "/get_claim_details",
            json=basic_request_body,
            params={"claim_uid": approved_claim_uid},
        )

        assert response.status_code == 200
        data = response.json()

        # Should return single claim
        assert len(data["claims"]) == 1
        claim = data["claims"][0]

        # Check structure
        assert claim["identifiers"]["uniqueId"] == approved_claim_uid
        assert_claim_structure(claim)

        # Should have service lines
        assert "lineItems" in claim
        assert claim["lineItems"] is not None
        assert len(claim["lineItems"]) > 0

        # Check service line structure
        service_line = claim["lineItems"][0]
        assert "procedure" in service_line
        assert "diagnosisSets" in service_line
        assert service_line["procedure"]["code"] == "99213"

        # Should have EOBs for approved claim
        assert "explanations" in claim
        assert claim["explanations"] is not None
        assert len(claim["explanations"]) > 0

        # Check EOB structure
        eob = claim["explanations"][0]
        assert "identifiers" in eob
        assert "payment" in eob
        assert (
            eob["payment"]["checkNumber"] is not None
        )  # Approved claims have payment references

    def test_denied_claim(self, client, basic_request_body, denied_claim_uid):
        """Test Case 2: Denied claim has correct financial structure."""
        response = client.post(
            "/get_claim_details",
            json=basic_request_body,
            params={"claim_uid": denied_claim_uid},
        )

        assert response.status_code == 200
        data = response.json()

        claim = data["claims"][0]
        assert claim["identifiers"]["uniqueId"] == denied_claim_uid
        assert claim["classification"]["status"]["identifier"] == "DND"

        # Denied claims: uncovered = responsibility, payment = 0
        financial = claim["financial"]
        assert (
            financial["allocation"]["excluded"]
            == financial["allocation"]["patientShare"]
        )
        assert financial["payment"]["disbursed"] == "0.00"

    def test_unauthorized_access(self, client, jane_member_id, approved_claim_uid):
        """Test Case 3: Cannot access another member's claim."""
        response = client.post(
            "/get_claim_details",
            json={"memberId": jane_member_id},
            params={"claim_uid": approved_claim_uid},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_nonexistent_claim(self, client, basic_request_body):
        """Test Case 4: Nonexistent claim returns 404."""
        response = client.post(
            "/get_claim_details",
            json=basic_request_body,
            params={"claim_uid": "NONEXISTENT-CLAIM-UID"},
        )

        assert response.status_code == 404

    def test_pending_claim(self, client, basic_request_body, pending_claim_uid):
        """Test Case 5: Pending claim has no payment information."""
        response = client.post(
            "/get_claim_details",
            json=basic_request_body,
            params={"claim_uid": pending_claim_uid},
        )

        assert response.status_code == 200
        claim = response.json()["claims"][0]

        assert claim["classification"]["status"]["identifier"] == "PEND"
        assert claim["financial"]["payment"]["disbursed"] == "0.00"


class TestGetClaimEobPdf:
    """Tests for POST /get_claim_eob_pdf endpoint."""

    def test_approved_claim_with_eob(
        self, client, basic_request_body, approved_claim_uid
    ):
        """Test Case 1: Approved claim returns EOB PDF information."""
        response = client.post(
            "/get_claim_eob_pdf",
            json=basic_request_body,
            params={"clm_uid": approved_claim_uid},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "identifiers" in data
        assert "uniqueId" in data["identifiers"]
        assert data["identifiers"]["uniqueId"] == approved_claim_uid
        assert "explanations" in data

        # Should have at least one EOB
        assert len(data["explanations"]) > 0

        # Check EOB item structure
        eob = data["explanations"][0]
        assert "documentId" in eob
        assert "documentUrl" in eob
        assert "contentType" in eob
        assert "fileSize" in eob

        # Validate values
        assert eob["contentType"] == "application/pdf"
        assert eob["fileSize"] > 0
        assert "https://example.health/eob/" in eob["documentUrl"]
        assert eob["documentUrl"].endswith(".pdf")

    def test_denied_claim_no_eob(self, client, basic_request_body, denied_claim_uid):
        """Test Case 2: Denied claim may have empty EOBs array."""
        response = client.post(
            "/get_claim_eob_pdf",
            json=basic_request_body,
            params={"clm_uid": denied_claim_uid},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["identifiers"]["uniqueId"] == denied_claim_uid
        assert "explanations" in data
        # Denied claims typically have no EOBs or empty array
        assert isinstance(data["explanations"], list)

    def test_unauthorized_access(self, client, jane_member_id, approved_claim_uid):
        """Test Case 3: Cannot access another member's EOB."""
        response = client.post(
            "/get_claim_eob_pdf",
            json={"memberId": jane_member_id},
            params={"clm_uid": approved_claim_uid},
        )

        assert response.status_code == 403
        assert "does not belong" in response.json()["detail"].lower()

    def test_nonexistent_claim(self, client, basic_request_body):
        """Test Case 4: Nonexistent claim returns 404."""
        response = client.post(
            "/get_claim_eob_pdf",
            json=basic_request_body,
            params={"clm_uid": "NONEXISTENT-CLAIM-UID"},
        )

        assert response.status_code == 404

    def test_processing_claim(self, client, basic_request_body, processing_claim_uid):
        """Test Case 5: Processing claim may have EOBs."""
        response = client.post(
            "/get_claim_eob_pdf",
            json=basic_request_body,
            params={"clm_uid": processing_claim_uid},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["identifiers"]["uniqueId"] == processing_claim_uid
        assert "explanations" in data

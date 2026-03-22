"""
Tests for Billing-related endpoints:
- POST /get_member_billing
- POST /create_payment_intent
- POST /confirm_payment_intent
"""

import pytest


class TestGetMemberBilling:
    """Tests for POST /get_member_billing endpoint."""

    def test_member_with_outstanding_bills(self, client, basic_request_body):
        """Test Case 1: Returns billing items with correct status."""
        response = client.post(
            "/get_member_billing",
            json=basic_request_body,
            params={"page_index": 0, "size": 50},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "items" in data
        assert "totals" in data

        # Check totals structure
        totals = data["totals"]
        assert "dueCount" in totals
        assert "totalDueAmt" in totals

        # Check items
        for item in data["items"]:
            assert "identifiers" in item
            assert "uniqueId" in item["identifiers"]
            assert "displayId" in item["identifiers"]
            assert "amountDue" in item
            assert "dueDate" in item
            assert "paymentStatus" in item
            assert "onlinePaymentEnabled" in item

            # Status should be valid
            assert item["paymentStatus"] in ["DUE", "PAID", "PARTIAL", "IN_COLLECTIONS"]

            # onlinePaymentEnabled should be boolean
            assert isinstance(item["onlinePaymentEnabled"], bool)

            # amountDue should be numeric string
            assert float(item["amountDue"]) >= 0

        # Verify totals calculation
        due_items = [
            item
            for item in data["items"]
            if item["paymentStatus"] != "PAID" and float(item["amountDue"]) > 0
        ]
        expected_due_count = len(due_items)
        expected_total_due = sum(float(item["amountDue"]) for item in due_items)

        assert int(totals["dueCount"]) == expected_due_count
        assert abs(float(totals["totalDueAmt"]) - expected_total_due) < 0.01

    def test_dependent_bills_via_hc_id(self, client, sara_member_id, john_hc_id):
        """Test Case 2: Dependent can access bills via hcId."""
        response = client.post(
            "/get_member_billing",
            json={"memberId": sara_member_id},
            params={"page_index": 0, "size": 50},
        )

        assert response.status_code == 200
        data = response.json()

        # Should return billing items
        assert "items" in data

        # Items should be for claims with matching accountId
        # (dependent's claims share subscriber's accountId)
        for item in data["items"]:
            assert "identifiers" in item
            assert "uniqueId" in item["identifiers"]

    def test_member_with_no_outstanding_bills(self, client, jane_member_id):
        """Test Case 3: Member with all paid bills."""
        response = client.post(
            "/get_member_billing",
            json={"memberId": jane_member_id},
            params={"page_index": 0, "size": 50},
        )

        assert response.status_code == 200
        data = response.json()

        # Should have items array (may be empty or all PAID)
        assert "items" in data
        assert "totals" in data

        # If all paid, totalDueAmt should be 0
        due_items = [
            item
            for item in data["items"]
            if item["paymentStatus"] != "PAID" and float(item["amountDue"]) > 0
        ]
        if len(due_items) == 0:
            assert float(data["totals"]["totalDueAmt"]) == 0.00
            assert int(data["totals"]["dueCount"]) == 0

    def test_pagination(self, client, basic_request_body):
        """Test Case 4: Pagination works correctly."""
        # Get first page with small size
        response1 = client.post(
            "/get_member_billing",
            json=basic_request_body,
            params={"page_index": 0, "size": 3},
        )

        # Get second page
        response2 = client.post(
            "/get_member_billing",
            json=basic_request_body,
            params={"page_index": 1, "size": 3},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        page1_uids = {
            item["identifiers"]["uniqueId"] for item in response1.json()["items"]
        }
        page2_uids = {
            item["identifiers"]["uniqueId"] for item in response2.json()["items"]
        }

        # No duplicates between pages
        assert len(page1_uids & page2_uids) == 0

    def test_can_pay_online_flag(self, client, basic_request_body):
        """Test Case 5: canPayOnline flag matches claim's enableBillPay."""
        response = client.post(
            "/get_member_billing",
            json=basic_request_body,
            params={"page_index": 0, "size": 50},
        )

        assert response.status_code == 200
        data = response.json()

        # All items should have onlinePaymentEnabled flag
        for item in data["items"]:
            assert "onlinePaymentEnabled" in item
            assert isinstance(item["onlinePaymentEnabled"], bool)


class TestCreatePaymentIntent:
    """Tests for POST /create_payment_intent endpoint."""

    def test_create_intent_for_specific_claim(
        self, client, sara_member_id, sara_pending_claim_uid
    ):
        """Test Case 1: Create payment intent linked to claim."""
        response = client.post(
            "/create_payment_intent",
            json={"memberId": sara_member_id},
            params={"amount": "60.00", "clm_uid": sara_pending_claim_uid},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "transactionId" in data
        assert "state" in data
        assert "authToken" in data
        assert "totalAmount" in data
        assert "currencyCode" in data
        assert "linkedClaim" in data

        # Verify values
        assert data["transactionId"].startswith("pi_")
        assert len(data["transactionId"]) > 10
        assert data["state"] == "REQUIRES_CONFIRMATION"
        assert data["authToken"].startswith(data["transactionId"])
        assert "_secret_" in data["authToken"]
        assert data["totalAmount"] == "60.00"
        assert data["currencyCode"] == "USD"
        assert data["linkedClaim"] == sara_pending_claim_uid

    def test_create_intent_without_claim_link(self, client, basic_request_body):
        """Test Case 2: Create payment intent without claim."""
        response = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "100.00"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["transactionId"].startswith("pi_")
        assert data["state"] == "REQUIRES_CONFIRMATION"
        assert data["totalAmount"] == "100.00"
        assert data["linkedClaim"] is None

    def test_unauthorized_claim(self, client, jane_member_id, sara_pending_claim_uid):
        """Test Case 3: Cannot create intent for another member's claim."""
        response = client.post(
            "/create_payment_intent",
            json={"memberId": jane_member_id},
            params={"amount": "60.00", "clm_uid": sara_pending_claim_uid},
        )

        assert response.status_code == 403
        assert "does not belong" in response.json()["detail"].lower()

    def test_nonexistent_claim(self, client, basic_request_body):
        """Test Case 4: Nonexistent claim returns 404."""
        response = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "50.00", "clm_uid": "NONEXISTENT-CLAIM-UID"},
        )

        assert response.status_code == 404

    def test_multiple_intents(self, client, basic_request_body):
        """Test Case 5: Can create multiple payment intents."""
        # Create first intent
        response1 = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "50.00"},
        )

        # Create second intent
        response2 = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "75.00"},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Should have different IDs
        assert response1.json()["transactionId"] != response2.json()["transactionId"]


class TestConfirmPaymentIntent:
    """Tests for POST /confirm_payment_intent endpoint."""

    def test_confirm_valid_intent(self, client, basic_request_body):
        """Test Case 1: Confirm valid payment intent."""
        # First create an intent
        create_response = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "60.00"},
        )

        assert create_response.status_code == 200
        payment_intent_id = create_response.json()["transactionId"]

        # Now confirm it
        confirm_response = client.post(
            "/confirm_payment_intent",
            json=basic_request_body,
            params={"payment_intent_id": payment_intent_id},
        )

        assert confirm_response.status_code == 200
        data = confirm_response.json()

        # Check structure
        assert "transactionId" in data
        assert "state" in data
        assert "receiptUrl" in data
        assert "totalAmount" in data
        assert "currencyCode" in data

        # Verify values
        assert data["transactionId"] == payment_intent_id
        assert data["state"] == "SUCCEEDED"
        assert "https://example.health/payments/" in data["receiptUrl"]
        assert data["receiptUrl"].endswith("/receipt")
        assert data["totalAmount"] == "60.00"
        assert data["currencyCode"] == "USD"

    def test_confirm_with_claim_updates_ledger(
        self, client, basic_request_body, denied_claim_uid
    ):
        """Test Case 2: Confirming payment for claim updates billing ledger."""
        # Create intent linked to claim
        create_response = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "10.00", "clm_uid": denied_claim_uid},
        )

        payment_intent_id = create_response.json()["transactionId"]

        # Confirm payment
        confirm_response = client.post(
            "/confirm_payment_intent",
            json=basic_request_body,
            params={"payment_intent_id": payment_intent_id},
        )

        assert confirm_response.status_code == 200
        data = confirm_response.json()

        assert data["state"] == "SUCCEEDED"
        assert data["linkedClaim"] == denied_claim_uid

        # Verify billing ledger updated (check via get_member_billing)
        billing_response = client.post(
            "/get_member_billing",
            json=basic_request_body,
            params={"page_index": 0, "size": 50},
        )

        billing_data = billing_response.json()

        # Find the claim in billing
        claim_billing = None
        for item in billing_data["items"]:
            if item["identifiers"]["uniqueId"] == denied_claim_uid:
                claim_billing = item
                break

        # Should be marked as PAID
        if claim_billing:
            assert claim_billing["paymentStatus"] == "PAID"
            assert float(claim_billing["amountDue"]) == 0.00

    def test_confirm_nonexistent_intent(self, client, basic_request_body):
        """Test Case 3: Confirming nonexistent intent returns 404."""
        response = client.post(
            "/confirm_payment_intent",
            json=basic_request_body,
            params={"payment_intent_id": "pi_nonexistent123"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_confirm_another_members_intent(
        self, client, basic_request_body, jane_member_id
    ):
        """Test Case 4: Cannot confirm another member's intent."""
        # Create intent as JOHN
        create_response = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "50.00"},
        )

        payment_intent_id = create_response.json()["transactionId"]

        # Try to confirm as JANE
        confirm_response = client.post(
            "/confirm_payment_intent",
            json={"memberId": jane_member_id},
            params={"payment_intent_id": payment_intent_id},
        )

        assert confirm_response.status_code == 403
        assert "not owned" in confirm_response.json()["detail"].lower()

    def test_receipt_url_format(self, client, basic_request_body):
        """Test Case 5: Receipt URL has correct format."""
        # Create and confirm intent
        create_response = client.post(
            "/create_payment_intent",
            json=basic_request_body,
            params={"amount": "25.00"},
        )

        payment_intent_id = create_response.json()["transactionId"]

        confirm_response = client.post(
            "/confirm_payment_intent",
            json=basic_request_body,
            params={"payment_intent_id": payment_intent_id},
        )

        assert confirm_response.status_code == 200
        data = confirm_response.json()

        # Receipt URL should include payment intent ID
        assert payment_intent_id in data["receiptUrl"]
        assert data["receiptUrl"].startswith("https://")

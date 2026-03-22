"""
Tests for Member-related endpoints:
- POST /get_member_profile
- POST /set_member_preferences
"""

import pytest


class TestGetMemberProfile:
    """Tests for POST /get_member_profile endpoint."""

    def test_subscriber_profile(self, client, basic_request_body):
        """Test Case 1: Get subscriber profile with preferences."""
        response = client.post(
            "/get_member_profile",
            json=basic_request_body,
            params={"active_only": True, "pcp_provider_id": "PRV-0106"},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "member" in data
        assert "preferences" in data
        assert "pcpProviderId" in data

        # Check member details
        member = data["member"]
        assert "identity" in member
        assert "primaryId" in member["identity"]
        assert "identifiers" in member
        assert "accountId" in member["identifiers"]
        assert "givenName" in member
        assert "familyName" in member
        assert "birthDate" in member
        assert "relationship" in member

        # Subscriber should have SUBSCR relationship
        assert member["relationship"]["identifier"] == "SUBSCR"
        assert member["identity"]["primaryId"] == basic_request_body["memberId"]

        # Check preferences
        preferences = data["preferences"]
        assert "language" in preferences
        assert "emailOptIn" in preferences
        assert "smsOptIn" in preferences

        # Verify types
        assert isinstance(preferences["emailOptIn"], bool)
        assert isinstance(preferences["smsOptIn"], bool)

        # Check PCP provider ID
        assert data["pcpProviderId"] == "PRV-0106"

    def test_dependent_profile(self, client, sara_member_id, john_hc_id):
        """Test Case 2: Get dependent profile."""
        response = client.post(
            "/get_member_profile",
            json={"memberId": sara_member_id},
            params={"active_only": True},
        )

        assert response.status_code == 200
        data = response.json()

        member = data["member"]
        assert member["identity"]["primaryId"] == sara_member_id
        assert member["relationship"]["identifier"] == "CHILD"
        assert member["identifiers"]["accountId"] == john_hc_id

        # Should have preferences for this member
        assert "preferences" in data

    def test_include_inactive_coverage(self, client, basic_request_body):
        """Test Case 3: Include inactive coverage members."""
        response = client.post(
            "/get_member_profile",
            json=basic_request_body,
            params={"active_only": False},
        )

        assert response.status_code == 200
        data = response.json()

        # Should return profile
        assert "member" in data

        # May include additional household members from past coverage
        # (implementation detail - just verify it doesn't error)

    def test_default_pcp_provider(self, client, basic_request_body):
        """Test Case 4: Default PCP provider ID when not specified."""
        response = client.post(
            "/get_member_profile", json=basic_request_body, params={"active_only": True}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have pcpProviderId (may be None or default value)
        assert "pcpProviderId" in data

    def test_nonexistent_member(self, client):
        """Test Case 5: Nonexistent member returns 404."""
        response = client.post(
            "/get_member_profile",
            json={"memberId": "NONEXISTENT-MEMBER"},
            params={"active_only": True},
        )

        assert response.status_code == 404

    def test_jane_profile(self, client, jane_member_id):
        """Test Case 6: Get JANE's profile (different plan)."""
        response = client.post(
            "/get_member_profile",
            json={"memberId": jane_member_id},
            params={"active_only": True},
        )

        assert response.status_code == 200
        data = response.json()

        member = data["member"]
        assert member["identity"]["primaryId"] == jane_member_id
        assert member["relationship"]["identifier"] == "SUBSCR"

        # Should have preferences
        preferences = data["preferences"]
        assert "language" in preferences


class TestSetMemberPreferences:
    """Tests for POST /set_member_preferences endpoint."""

    def test_update_language_preference(self, client, basic_request_body):
        """Test Case 1: Update language preference only."""
        response = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"language": "es-us"},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "language" in data
        assert "emailOptIn" in data
        assert "smsOptIn" in data

        # Language should be updated
        assert data["language"] == "es-us"

        # Other preferences should be unchanged (boolean values)
        assert isinstance(data["emailOptIn"], bool)
        assert isinstance(data["smsOptIn"], bool)

    def test_update_multiple_preferences(self, client, basic_request_body):
        """Test Case 2: Update multiple preferences at once."""
        response = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"language": "en-us", "emailOptIn": True, "smsOptIn": True},
        )

        assert response.status_code == 200
        data = response.json()

        # All specified preferences should be updated
        assert data["language"] == "en-us"
        assert data["emailOptIn"] is True
        assert data["smsOptIn"] is True

    def test_partial_update(self, client, basic_request_body):
        """Test Case 3: Partial update preserves other preferences."""
        # First, set initial preferences
        initial_response = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"language": "en-us", "emailOptIn": True, "smsOptIn": False},
        )

        assert initial_response.status_code == 200
        initial_data = initial_response.json()

        # Now update only emailOptIn
        update_response = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"emailOptIn": False},
        )

        assert update_response.status_code == 200
        updated_data = update_response.json()

        # emailOptIn should be updated
        assert updated_data["emailOptIn"] is False

        # Other preferences should remain unchanged
        assert updated_data["language"] == initial_data["language"]
        assert updated_data["smsOptIn"] == initial_data["smsOptIn"]

    def test_dependent_preferences(self, client, sara_member_id):
        """Test Case 4: Update dependent's preferences independently."""
        response = client.post(
            "/set_member_preferences",
            json={"memberId": sara_member_id},
            params={"language": "en-us", "emailOptIn": False},
        )

        assert response.status_code == 200
        data = response.json()

        # Preferences should be updated for dependent
        assert data["language"] == "en-us"
        assert data["emailOptIn"] is False

        # Verify by getting profile
        profile_response = client.post(
            "/get_member_profile",
            json={"memberId": sara_member_id},
            params={"active_only": True},
        )

        assert profile_response.status_code == 200
        profile_data = profile_response.json()

        # Preferences should match what we set
        assert profile_data["preferences"]["language"] == "en-us"
        assert profile_data["preferences"]["emailOptIn"] is False

    def test_toggle_email_opt_in(self, client, basic_request_body):
        """Test Case 5: Toggle email opt-in preference."""
        # Set to True
        response1 = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"emailOptIn": True},
        )

        assert response1.status_code == 200
        assert response1.json()["emailOptIn"] is True

        # Toggle to False
        response2 = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"emailOptIn": False},
        )

        assert response2.status_code == 200
        assert response2.json()["emailOptIn"] is False

    def test_toggle_sms_opt_in(self, client, basic_request_body):
        """Test Case 6: Toggle SMS opt-in preference."""
        # Set to True
        response1 = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"smsOptIn": True},
        )

        assert response1.status_code == 200
        assert response1.json()["smsOptIn"] is True

        # Toggle to False
        response2 = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"smsOptIn": False},
        )

        assert response2.status_code == 200
        assert response2.json()["smsOptIn"] is False

    def test_language_options(self, client, basic_request_body):
        """Test Case 7: Test different language options."""
        languages = ["en-us", "en-ca", "es-us"]

        for lang in languages:
            response = client.post(
                "/set_member_preferences",
                json=basic_request_body,
                params={"language": lang},
            )

            assert response.status_code == 200
            assert response.json()["language"] == lang

    def test_preferences_persistence(self, client, basic_request_body):
        """Test Case 8: Preferences persist across get/set operations."""
        # Set preferences
        set_response = client.post(
            "/set_member_preferences",
            json=basic_request_body,
            params={"language": "es-us", "emailOptIn": True, "smsOptIn": False},
        )

        assert set_response.status_code == 200

        # Get profile to verify persistence
        profile_response = client.post(
            "/get_member_profile", json=basic_request_body, params={"active_only": True}
        )

        assert profile_response.status_code == 200
        preferences = profile_response.json()["preferences"]

        # Should match what we set
        assert preferences["language"] == "es-us"
        assert preferences["emailOptIn"] is True
        assert preferences["smsOptIn"] is False

    def test_missing_member_id(self, client):
        """Test Case 9: Missing memberId returns error."""
        response = client.post(
            "/set_member_preferences", json={}, params={"language": "en-us"}
        )

        assert response.status_code == 422  # Validation error

    def test_jane_preferences(self, client, jane_member_id):
        """Test Case 10: Update JANE's preferences."""
        response = client.post(
            "/set_member_preferences",
            json={"memberId": jane_member_id},
            params={"language": "en-ca", "emailOptIn": False, "smsOptIn": True},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["language"] == "en-ca"
        assert data["emailOptIn"] is False
        assert data["smsOptIn"] is True

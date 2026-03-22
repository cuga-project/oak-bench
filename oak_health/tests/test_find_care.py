"""
Tests for Find Care endpoints:
- POST /find_care_specialty
- POST /find_care_suggestions
"""

import pytest


class TestFindCareSpecialty:
    """Tests for POST /find_care_specialty endpoint."""

    def test_primary_care_search(
        self, client, request_with_location, john_contract_uid, john_location_params
    ):
        """Test Case 1: Search for primary care providers."""
        response = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "20",
                "page_index": 0,
                "size": 5,
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "providers" in data
        assert len(data["providers"]) <= 5

        # Check provider structure
        for provider in data["providers"]:
            assert "providerId" in provider
            assert "name" in provider
            assert "address" in provider
            assert "expertise" in provider
            assert "network" in provider

            # Check location details
            address = provider["address"]
            assert "coordinates" in address
            coordinates = address["coordinates"]
            assert "distanceMiles" in coordinates
            assert coordinates["distanceMiles"] >= 0

            # Check specialty
            expertise = provider["expertise"]
            assert "specialtyCategories" in expertise
            assert "25" in expertise["specialtyCategories"]

            # Check network status
            network = provider["network"]
            assert "status" in network
            assert "accept_new_patients" in network
            assert "coverages" in network
            assert "MED" in network["coverages"]

    def test_with_taxonomy_filter(
        self, client, request_with_location, john_contract_uid, john_location_params
    ):
        """Test Case 2: Filter by taxonomy codes."""
        response = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "taxonomy_codes": ["261QP2300X"],
                "distance": "20",
                "page_index": 0,
                "size": 5,
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # All providers should have the specified taxonomy
        for provider in data["providers"]:
            taxonomies = provider["expertise"]["taxonomies"]
            taxonomy_codes = [t["code"] for t in taxonomies]
            assert "261QP2300X" in taxonomy_codes

    def test_missing_location(self, client, john_contract_uid):
        """Test Case 3: Missing location returns 400 — location is required, no automatic fallback."""
        no_location_body = {
            "memberId": "121231234"
        }  # known member, but no location provided
        response = client.post(
            "/find_care_specialty",
            json=no_location_body,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "20",
                "page_index": 0,
                "size": 5,
            },
        )

        assert response.status_code == 400
        assert "statecode" in response.json()["detail"].lower()

    def test_distance_filtering(
        self, client, request_with_location, john_contract_uid, john_location_params
    ):
        """Test Case 4: Distance parameter filters results."""
        # Search with 5 mile radius
        response_small = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "5",
                "page_index": 0,
                "size": 5,
                **john_location_params,
            },
        )

        # Search with 50 mile radius
        response_large = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "50",
                "page_index": 0,
                "size": 5,
                **john_location_params,
            },
        )

        assert response_small.status_code == 200
        assert response_large.status_code == 200

        small_count = len(response_small.json()["providers"])
        large_count = len(response_large.json()["providers"])

        # Larger radius should return same or more providers
        assert large_count >= small_count

        # All providers in small radius should be within 5 miles
        for provider in response_small.json()["providers"]:
            distance = provider["address"]["coordinates"]["distanceMiles"]
            assert distance <= 5.0

    def test_pagination(
        self, client, request_with_location, john_contract_uid, john_location_params
    ):
        """Test Case 5: Pagination works correctly."""
        # Get first page
        response1 = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "20",
                "page_index": 0,
                "size": 3,
                **john_location_params,
            },
        )

        # Get second page
        response2 = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "20",
                "page_index": 1,
                "size": 3,
                **john_location_params,
            },
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        page1_ids = {p["providerId"] for p in response1.json()["providers"]}
        page2_ids = {p["providerId"] for p in response2.json()["providers"]}

        # No duplicates between pages
        assert len(page1_ids & page2_ids) == 0

    def test_radiology_search(
        self, client, request_with_location, john_contract_uid, john_location_params
    ):
        """Test Case 6: Search for radiology/imaging providers."""
        response = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["231", "75"],
                "distance": "30",
                "page_index": 0,
                "size": 5,
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check that providers have radiology/imaging categories
        for provider in data["providers"]:
            categories = provider["expertise"]["specialtyCategories"]
            assert "231" in categories or "75" in categories

    def test_invalid_contract(
        self, client, request_with_location, john_location_params
    ):
        """Test Case 7: Invalid contract returns error."""
        response = client.post(
            "/find_care_specialty",
            json=request_with_location,
            params={
                "contract_uid": "INVALID-CONTRACT",
                "brand_code": "ACME",
                "specialty_category_codes": ["25"],
                "distance": "20",
                "page_index": 0,
                "size": 5,
                **john_location_params,
            },
        )

        assert response.status_code == 403


class TestFindCareSuggestions:
    """Tests for POST /find_care_suggestions endpoint."""

    def test_primary_care_suggestion(
        self, client, request_with_location, john_location_params
    ):
        """Test Case 1: Primary care search returns specialty suggestions."""
        response = client.post(
            "/find_care_suggestions",
            json=request_with_location,
            params={
                "search_text": "primary care doctor",
                "brand_code": "ACME",
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "primarySearchIntent" in data
        assert "suggestionList" in data
        assert "locationDetails" in data

        # Should be SPECIALTY intent
        assert data["primarySearchIntent"] == "SPECIALTY"

        # Check suggestions
        assert len(data["suggestionList"]) > 0
        suggestion = data["suggestionList"][0]

        assert "text" in suggestion
        assert "type" in suggestion
        assert "score" in suggestion
        assert "criteria" in suggestion
        assert "dplQueryParams" in suggestion

        # Check criteria
        criteria = suggestion["criteria"]
        assert "taxonomyList" in criteria
        assert "specialtyCategoryList" in criteria

        # Should have primary care taxonomies
        taxonomy_codes = [t["code"] for t in criteria["taxonomyList"]]
        assert "261QP2300X" in taxonomy_codes or "207Q00000X" in taxonomy_codes

        # Check dplQueryParams are personalized
        params = suggestion["dplQueryParams"]
        assert "brand_code" in params
        assert params["brand_code"] == "ACME"

        # Check location details
        location = data["locationDetails"]
        assert "zipCode" in location
        assert location["locationType"] == "ZIP_CODE"

    def test_mri_suggestion(self, client, request_with_location, john_location_params):
        """Test Case 2: MRI search returns procedure suggestions."""
        response = client.post(
            "/find_care_suggestions",
            json=request_with_location,
            params={
                "search_text": "mri",
                "brand_code": "ACME",
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should be PROCEDURE intent
        assert data["primarySearchIntent"] == "PROCEDURE"

        # Check suggestion
        suggestion = data["suggestionList"][0]
        assert suggestion["type"] == "PROCEDURE"

        # Should have procedure code
        assert "procedureCode" in suggestion
        assert suggestion["procedureCode"] is not None

    def test_knee_surgery_suggestion(
        self, client, request_with_location, john_location_params
    ):
        """Test Case 3: Knee surgery search returns procedure suggestions."""
        response = client.post(
            "/find_care_suggestions",
            json=request_with_location,
            params={
                "search_text": "knee surgery",
                "brand_code": "ACME",
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["primarySearchIntent"] == "PROCEDURE"

        suggestion = data["suggestionList"][0]
        assert "procedureCode" in suggestion

        # Should have orthopedic taxonomy
        criteria = suggestion["criteria"]
        taxonomy_codes = [t["code"] for t in criteria["taxonomyList"]]
        assert "207X00000X" in taxonomy_codes

    def test_radiology_suggestion(
        self, client, request_with_location, john_location_params
    ):
        """Test Case 4: Radiology search returns specialty suggestions."""
        response = client.post(
            "/find_care_suggestions",
            json=request_with_location,
            params={
                "search_text": "radiology",
                "brand_code": "ACME",
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["primarySearchIntent"] == "SPECIALTY"

        suggestion = data["suggestionList"][0]
        criteria = suggestion["criteria"]

        # Should have radiology categories
        category_codes = [c["identifier"] for c in criteria["specialtyCategoryList"]]
        assert "231" in category_codes or "75" in category_codes

    def test_missing_location(self, client):
        """Test Case 5: Missing location returns 400 — location is required, no automatic fallback."""
        no_location_body = {
            "memberId": "121231234"
        }  # known member, but no location provided
        response = client.post(
            "/find_care_suggestions",
            json=no_location_body,
            params={"search_text": "primary care", "brand_code": "ACME"},
        )

        assert response.status_code == 400
        assert "statecode" in response.json()["detail"].lower()

    def test_default_to_primary_care(
        self, client, request_with_location, john_location_params
    ):
        """Test Case 6: Unknown search defaults to primary care."""
        response = client.post(
            "/find_care_suggestions",
            json=request_with_location,
            params={
                "search_text": "random unknown search",
                "brand_code": "ACME",
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should default to SPECIALTY (primary care)
        assert data["primarySearchIntent"] == "SPECIALTY"

        # Should have primary care suggestions
        suggestion = data["suggestionList"][0]
        criteria = suggestion["criteria"]
        category_codes = [c["identifier"] for c in criteria["specialtyCategoryList"]]
        assert "25" in category_codes

    def test_location_details_populated(
        self, client, request_with_location, john_location_params
    ):
        """Test Case 7: Location details are properly populated."""
        response = client.post(
            "/find_care_suggestions",
            json=request_with_location,
            params={
                "search_text": "primary care",
                "brand_code": "ACME",
                **john_location_params,
            },
        )

        assert response.status_code == 200
        data = response.json()

        location = data["locationDetails"]
        assert location["zipCode"] == john_location_params["zipCode"]
        assert location["stateCode"] == john_location_params["stateCode"]
        assert location["locationType"] == "ZIP_CODE"


class TestLocationViaQueryParams:
    """Tests that stateCode/zipCode can be passed as query params (agent-friendly path)."""

    def test_find_care_suggestions_with_query_params(self, client, basic_request_body):
        """stateCode/zipCode as query params should work without body location."""
        response = client.post(
            "/find_care_suggestions",
            json=basic_request_body,
            params={
                "search_text": "mri",
                "brand_code": "ACME",
                "stateCode": "NY",
                "zipCode": "11211",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["primarySearchIntent"] == "PROCEDURE"
        assert len(data["suggestionList"]) > 0
        assert data["locationDetails"]["stateCode"] == "NY"

    def test_find_care_specialty_with_query_params(
        self, client, basic_request_body, john_contract_uid
    ):
        """stateCode/zipCode as query params should work without body location."""
        response = client.post(
            "/find_care_specialty",
            json=basic_request_body,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": ["75"],
                "taxonomy_codes": ["261QR0200X"],
                "distance": "30",
                "page_index": 0,
                "size": 5,
                "stateCode": "NY",
                "zipCode": "11211",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        provider_names = [p["name"] for p in data["providers"]]
        assert "Sophia Ramirez" in provider_names

    def test_mri_full_flow_via_query_params(
        self, client, basic_request_body, john_contract_uid
    ):
        """Full find-care flow using query params for location (mimics agent calling convention)."""
        # Step 1 - suggestions
        r1 = client.post(
            "/find_care_suggestions",
            json=basic_request_body,
            params={
                "search_text": "mri",
                "brand_code": "ACME",
                "stateCode": "NY",
                "zipCode": "11211",
            },
        )
        assert r1.status_code == 200
        suggestion = r1.json()["suggestionList"][0]
        specialty_codes = [
            c["identifier"] for c in suggestion["criteria"]["specialtyCategoryList"]
        ]
        taxonomy_codes = [
            t["code"] for t in suggestion["criteria"]["taxonomyList"]
        ] or None
        distance = suggestion["dplQueryParams"].get("distance", "20")

        # Step 2 - providers
        r2 = client.post(
            "/find_care_specialty",
            json=basic_request_body,
            params={
                "contract_uid": john_contract_uid,
                "brand_code": "ACME",
                "specialty_category_codes": specialty_codes,
                "taxonomy_codes": taxonomy_codes,
                "distance": distance,
                "page_index": 0,
                "size": 5,
                "stateCode": "NY",
                "zipCode": "11211",
            },
        )
        assert r2.status_code == 200
        provider_names = [p["name"] for p in r2.json()["providers"]]
        assert "Sophia Ramirez" in provider_names

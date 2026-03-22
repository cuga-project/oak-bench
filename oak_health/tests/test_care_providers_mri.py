"""
End-to-end API test that mimics the care_providers_mri benchmark task step by step.

Test case intent: "Find in-network care providers near me for an MRI scan"
Member context: member_id=121231234, location=NY/11211
Expected keyword: "Sophia Ramirez"

Flow (matching the policy):
  Step 1 - get_coverage_period  → extract contract_uid, brand_code
  Step 2 - find_care_suggestions → extract specialty_category_codes, taxonomy_codes, distance
  Step 3 - find_care_specialty   → assert Sophia Ramirez is in results
"""

import pytest


MEMBER_ID = "121231234"
LOCATION_PARAMS = {"stateCode": "NY", "zipCode": "11211"}
REQUEST_BODY = {"memberId": MEMBER_ID}


class TestCareProvidersMriFlow:
    """Step-by-step API flow for the care_providers_mri benchmark task."""

    def test_step1_get_coverage_period(self, client):
        """Step 1: Retrieve active coverage to extract contract_uid and brand_code."""
        response = client.post("/get_coverage_period", json=REQUEST_BODY)

        assert response.status_code == 200, (
            f"get_coverage_period failed: {response.json()}"
        )
        data = response.json()

        assert "eligibility" in data
        assert len(data["eligibility"]) > 0

        # Find the active coverage entry
        active_entry = next(
            (
                e
                for e in data["eligibility"]
                if any(p["status"]["identifier"] == "A" for p in e["periods"])
            ),
            None,
        )
        assert active_entry is not None, "No active eligibility entry found"

        contract_uid = active_entry["identifiers"]["contractUniqueId"]
        brand_code = active_entry["brand"]["identifier"]

        assert contract_uid == "CONTRACT-UID-JOHN-1001"
        assert brand_code == "ACME"

    def test_step2_find_care_suggestions_for_mri(self, client):
        """Step 2: Call find_care_suggestions with 'mri' to get specialty codes and distance."""
        response = client.post(
            "/find_care_suggestions",
            json=REQUEST_BODY,
            params={"search_text": "mri", "brand_code": "ACME", **LOCATION_PARAMS},
        )

        assert response.status_code == 200, (
            f"find_care_suggestions failed: {response.json()}"
        )
        data = response.json()

        assert data["primarySearchIntent"] == "PROCEDURE"
        assert len(data["suggestionList"]) > 0

        suggestion = data["suggestionList"][0]

        # Verify specialty category codes include "75" (Imaging Centers)
        category_codes = [
            c["identifier"] for c in suggestion["criteria"]["specialtyCategoryList"]
        ]
        assert "75" in category_codes, (
            f"Expected '75' in specialtyCategoryList, got: {category_codes}"
        )

        # Verify taxonomy codes include "261QR0200X" (Radiology Clinic/Center)
        taxonomy_codes = [t["code"] for t in suggestion["criteria"]["taxonomyList"]]
        assert "261QR0200X" in taxonomy_codes, (
            f"Expected '261QR0200X' in taxonomyList, got: {taxonomy_codes}"
        )

        # Verify dplQueryParams contains distance
        assert "distance" in suggestion["dplQueryParams"]
        assert suggestion["dplQueryParams"]["distance"] == "30"

        # Verify location details echo back the member's location
        loc = data["locationDetails"]
        assert loc["stateCode"] == "NY"
        assert loc["zipCode"] == "11211"

    def test_step3_find_care_specialty_returns_sophia_ramirez(self, client):
        """Step 3: Call find_care_specialty with codes from Step 2 and assert Sophia Ramirez is found."""
        response = client.post(
            "/find_care_specialty",
            json=REQUEST_BODY,
            params={
                "contract_uid": "CONTRACT-UID-JOHN-1001",
                "brand_code": "ACME",
                "specialty_category_codes": ["75"],  # from Step 2 suggestions
                "taxonomy_codes": ["261QR0200X"],  # from Step 2 suggestions
                "distance": "30",  # from Step 2 dplQueryParams
                "page_index": 0,
                "size": 5,
                **LOCATION_PARAMS,
            },
        )

        assert response.status_code == 200, (
            f"find_care_specialty failed: {response.json()}"
        )
        data = response.json()

        assert "providers" in data
        assert len(data["providers"]) > 0, (
            "No providers returned — Sophia Ramirez should be present"
        )

        provider_names = [p["name"] for p in data["providers"]]
        assert "Sophia Ramirez" in provider_names, (
            f"Expected 'Sophia Ramirez' in providers, got: {provider_names}"
        )

        # Validate Sophia Ramirez's details
        sophia = next(p for p in data["providers"] if p["name"] == "Sophia Ramirez")

        assert sophia["address"]["facilityName"] == "Vista Radiology Center"
        assert sophia["address"]["address"]["city"] == "Queens"
        assert sophia["address"]["address"]["stateCode"] == "NY"
        assert sophia["network"]["status"] == "TP_INNETWORK"
        assert sophia["network"]["accept_new_patients"] is True
        assert "75" in sophia["expertise"]["specialtyCategories"]

        # Distance should be 15 miles (same state, different zip)
        assert sophia["address"]["coordinates"]["distanceMiles"] == 15.0

    def test_full_flow_end_to_end(self, client):
        """
        Full end-to-end flow matching the care_providers_mri task exactly:
          Step 1 → get_coverage_period
          Step 2 → find_care_suggestions
          Step 3 → find_care_specialty
        Each step uses real outputs from the previous step (no hardcoded intermediate values).
        """
        # --- Step 1: get_coverage_period ---
        r1 = client.post("/get_coverage_period", json=REQUEST_BODY)
        assert r1.status_code == 200, f"Step 1 failed: {r1.json()}"
        coverage = r1.json()

        active_entry = next(
            (
                e
                for e in coverage["eligibility"]
                if any(p["status"]["identifier"] == "A" for p in e["periods"])
            ),
            None,
        )
        assert active_entry is not None, "Step 1: No active eligibility found"
        contract_uid = active_entry["identifiers"]["contractUniqueId"]
        brand_code = active_entry["brand"]["identifier"]

        # --- Step 2: find_care_suggestions ---
        r2 = client.post(
            "/find_care_suggestions",
            json=REQUEST_BODY,
            params={"search_text": "mri", "brand_code": brand_code, **LOCATION_PARAMS},
        )
        assert r2.status_code == 200, f"Step 2 failed: {r2.json()}"
        suggestions_data = r2.json()

        suggestion = suggestions_data["suggestionList"][0]
        specialty_codes = [
            c["identifier"] for c in suggestion["criteria"]["specialtyCategoryList"]
        ]
        taxonomy_codes = [t["code"] for t in suggestion["criteria"]["taxonomyList"]]
        distance = suggestion["dplQueryParams"].get("distance", "20")

        assert specialty_codes, (
            "Step 2: No specialty_category_codes extracted from suggestions"
        )

        # --- Step 3: find_care_specialty ---
        r3 = client.post(
            "/find_care_specialty",
            json=REQUEST_BODY,
            params={
                "contract_uid": contract_uid,
                "brand_code": brand_code,
                "specialty_category_codes": specialty_codes,
                "taxonomy_codes": taxonomy_codes if taxonomy_codes else None,
                "distance": distance,
                "page_index": 0,
                "size": 5,
                **LOCATION_PARAMS,
            },
        )
        assert r3.status_code == 200, f"Step 3 failed: {r3.json()}"
        providers_data = r3.json()

        provider_names = [p["name"] for p in providers_data["providers"]]
        assert "Sophia Ramirez" in provider_names, (
            f"care_providers_mri FAILED: 'Sophia Ramirez' not found.\n"
            f"  contract_uid={contract_uid}, brand_code={brand_code}\n"
            f"  specialty_codes={specialty_codes}, taxonomy_codes={taxonomy_codes}, distance={distance}\n"
            f"  providers returned: {provider_names}"
        )

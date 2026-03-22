"""
Tests for Coverage-related endpoints:
- POST /get_coverage_period
- POST /get_plan_information
- POST /get_benefit_accumulators
"""

import pytest


class TestGetCoveragePeriod:
    """Tests for POST /get_coverage_period endpoint."""

    def test_active_coverage(self, client, basic_request_body):
        """Test Case 1: Returns active and inactive coverage periods."""
        response = client.post("/get_coverage_period", json=basic_request_body)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "eligibility" in data
        assert len(data["eligibility"]) > 0

        eligibility = data["eligibility"][0]
        assert "identifiers" in eligibility
        assert "accountId" in eligibility["identifiers"]
        assert "contractNumber" in eligibility["identifiers"]
        assert "periods" in eligibility

        # Should have multiple coverage periods (2024, 2025)
        assert len(eligibility["periods"]) >= 2

        # Check for active 2025 coverage
        active_coverage = None
        inactive_coverage = None

        for cov in eligibility["periods"]:
            assert "periodKey" in cov
            assert "dates" in cov
            assert "status" in cov
            assert "enrollees" in cov

            if cov["status"]["identifier"] == "A":
                active_coverage = cov
            elif cov["status"]["identifier"] == "I":
                inactive_coverage = cov

        # Should have at least one active coverage
        assert active_coverage is not None
        assert active_coverage["dates"]["start"].startswith("2025")

        # Check member list in active coverage
        assert len(active_coverage["enrollees"]) >= 3  # Subscriber + 2 dependents

        # Verify subscriber exists
        subscriber = None
        for member in active_coverage["enrollees"]:
            if member["relationship"]["identifier"] == "SUBSCR":
                subscriber = member
                break

        assert subscriber is not None
        assert "personId" in subscriber
        assert "name" in subscriber
        assert "given" in subscriber["name"]
        assert "family" in subscriber["name"]

    def test_dependent_access(self, client, john_member_id, john_hc_id):
        """Test Case 2: Can access via hcId (shared by dependents)."""
        response = client.post("/get_coverage_period", json={"memberId": john_hc_id})

        assert response.status_code == 200
        data = response.json()

        # Should return eligibility
        eligibility = data["eligibility"][0]
        assert eligibility["identifiers"]["accountId"] == john_hc_id

        # Should show all family members
        active_coverage = None
        for cov in eligibility["periods"]:
            if cov["status"]["identifier"] == "A":
                active_coverage = cov
                break

        assert active_coverage is not None

        # Verify members are present
        assert len(active_coverage["enrollees"]) >= 1

    def test_coverage_by_hc_id(self, client, john_hc_id):
        """Test Case 3: Can retrieve coverage using accountId."""
        response = client.post("/get_coverage_period", json={"memberId": john_hc_id})

        assert response.status_code == 200
        data = response.json()

        eligibility = data["eligibility"][0]
        assert eligibility["identifiers"]["accountId"] == john_hc_id

    def test_missing_member_id(self, client):
        """Test Case 4: Missing memberId returns error."""
        response = client.post("/get_coverage_period", json={})

        assert response.status_code == 422  # Validation error

    def test_nonexistent_member(self, client):
        """Test Case 5: Nonexistent member returns 404."""
        response = client.post(
            "/get_coverage_period", json={"memberId": "NONEXISTENT-MEMBER"}
        )

        assert response.status_code == 404


class TestGetPlanInformation:
    """Tests for POST /get_plan_information endpoint."""

    def test_active_plan_details(
        self, client, basic_request_body, john_coverage_key_2025
    ):
        """Test Case 1: Returns complete plan information."""
        response = client.post(
            "/get_plan_information",
            json=basic_request_body,
            params={"coverage_key": john_coverage_key_2025, "opted_plan_type": "MED"},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "contractCd" in data
        assert "contractState" in data
        assert "marketSegment" in data
        assert "planType" in data
        assert "benefitPeriod" in data
        assert "network" in data

        # Verify benefit period
        assert data["benefitPeriod"]["cd"] == "CalendarYear"

        # Check network structures
        assert len(data["network"]) > 0

        # Find specific networks
        networks = {net["cd"]: net for net in data["network"]}

        # Should have ALL, HMO, PAR networks
        assert "ALL" in networks
        assert "HMO" in networks or "PAR" in networks

        # Check HMO network cost shares
        if "HMO" in networks:
            hmo = networks["HMO"]
            assert "costShare" in hmo
            assert len(hmo["costShare"]) > 0

            # Find deductibles and OOP max
            cost_shares = {
                cs["benefit"]["optionNm"]: cs
                for cs in hmo["costShare"]
                if "optionNm" in cs["benefit"]
            }

            # Verify individual deductible
            if "CINDDEDDOL" in cost_shares:
                ind_ded = cost_shares["CINDDEDDOL"]
                assert ind_ded["benefit"]["value"] == "250"
                assert ind_ded["benefit"]["unit"] == "Dollar(S)"

            # Verify family deductible
            if "CFAMDEDDOL" in cost_shares:
                fam_ded = cost_shares["CFAMDEDDOL"]
                assert fam_ded["benefit"]["value"] == "500"

    def test_invalid_coverage_key(self, client, basic_request_body):
        """Test Case 2: Invalid coverage key returns 404."""
        response = client.post(
            "/get_plan_information",
            json=basic_request_body,
            params={"coverage_key": "INVALID-KEY", "opted_plan_type": "MED"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_unauthorized_coverage_access(
        self, client, jane_member_id, john_coverage_key_2025
    ):
        """Test Case 3: Cannot access another member's plan."""
        response = client.post(
            "/get_plan_information",
            json={"memberId": jane_member_id},
            params={"coverage_key": john_coverage_key_2025, "opted_plan_type": "MED"},
        )

        assert response.status_code == 403
        assert "does not belong" in response.json()["detail"].lower()

    def test_access_via_hc_id(self, client, john_hc_id, john_coverage_key_2025):
        """Test Case 4: Can access plan via hcId (shared by family)."""
        response = client.post(
            "/get_plan_information",
            json={"memberId": john_hc_id},
            params={"coverage_key": john_coverage_key_2025, "opted_plan_type": "MED"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "network" in data

    def test_inactive_coverage_plan(
        self, client, basic_request_body, john_coverage_key_2024
    ):
        """Test Case 5: Can retrieve plan for inactive coverage."""
        response = client.post(
            "/get_plan_information",
            json=basic_request_body,
            params={"coverage_key": john_coverage_key_2024, "opted_plan_type": "MED"},
        )

        assert response.status_code == 200
        data = response.json()

        # Should return 2024 plan details
        assert data["startDt"] == "2024-01-01"
        assert data["endDt"] == "2024-12-31"


class TestGetBenefitAccumulators:
    """Tests for POST /get_benefit_accumulators endpoint."""

    def test_active_coverage_accumulators(
        self, client, basic_request_body, john_coverage_key_2025
    ):
        """Test Case 1: Returns accumulators for active coverage."""
        response = client.post(
            "/get_benefit_accumulators",
            json=basic_request_body,
            params={"coverage_key": john_coverage_key_2025},
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "planYear" in data
        assert "periodId" in data
        assert "tracking" in data

        assert data["planYear"] == "2025"
        assert data["periodId"] == john_coverage_key_2025

        # Check accumulators
        tracking = data["tracking"]
        assert len(tracking) > 0

        # Group by category/scope/tier
        acc_map = {}
        for acc in tracking:
            assert "category" in acc
            assert "scope" in acc
            assert "tier" in acc
            assert "accumulated" in acc
            assert "maximum" in acc

            key = (acc["category"], acc["scope"], acc["tier"])
            acc_map[key] = acc

        # Verify specific accumulators exist
        # Individual deductible in-network
        assert ("DED", "INDV", "INN") in acc_map
        ind_ded_inn = acc_map[("DED", "INDV", "INN")]
        assert float(ind_ded_inn["accumulated"]) == 250.00
        assert float(ind_ded_inn["maximum"]) == 1000.00

        # Individual OOP in-network
        assert ("OOP", "INDV", "INN") in acc_map
        ind_oop_inn = acc_map[("OOP", "INDV", "INN")]
        assert float(ind_oop_inn["accumulated"]) == 400.00
        assert float(ind_oop_inn["maximum"]) == 3000.00

        # Family deductible in-network
        assert ("DED", "FAM", "INN") in acc_map
        fam_ded_inn = acc_map[("DED", "FAM", "INN")]
        assert float(fam_ded_inn["accumulated"]) == 700.00
        assert float(fam_ded_inn["maximum"]) == 3000.00

        # Should also have OON accumulators
        assert ("DED", "INDV", "OON") in acc_map
        assert ("OOP", "INDV", "OON") in acc_map

    def test_access_via_hc_id(self, client, john_hc_id, john_coverage_key_2025):
        """Test Case 2: Can access accumulators via hcId (shared by family)."""
        response = client.post(
            "/get_benefit_accumulators",
            json={"memberId": john_hc_id},
            params={"coverage_key": john_coverage_key_2025},
        )

        assert response.status_code == 200
        data = response.json()

        # Should return accumulators
        assert data["periodId"] == john_coverage_key_2025
        assert len(data["tracking"]) > 0

        # Family-level accumulators are shared
        fam_accumulators = [a for a in data["tracking"] if a["scope"] == "FAM"]
        assert len(fam_accumulators) > 0

    def test_invalid_coverage_key(self, client, basic_request_body):
        """Test Case 3: Invalid coverage key returns 404."""
        response = client.post(
            "/get_benefit_accumulators",
            json=basic_request_body,
            params={"coverage_key": "INVALID-KEY"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_unauthorized_coverage(
        self, client, jane_member_id, john_coverage_key_2025
    ):
        """Test Case 4: Cannot access another member's accumulators."""
        response = client.post(
            "/get_benefit_accumulators",
            json={"memberId": jane_member_id},
            params={"coverage_key": john_coverage_key_2025},
        )

        assert response.status_code == 403
        assert "does not belong" in response.json()["detail"].lower()

    def test_jane_coverage_accumulators(
        self, client, jane_member_id, jane_coverage_key_2025
    ):
        """Test Case 5: JANE's HMO plan has different accumulator structure."""
        response = client.post(
            "/get_benefit_accumulators",
            json={"memberId": jane_member_id},
            params={"coverage_key": jane_coverage_key_2025},
        )

        assert response.status_code == 200
        data = response.json()

        tracking = data["tracking"]
        acc_map = {(a["category"], a["scope"], a["tier"]): a for a in tracking}

        # JANE's plan: no deductible (maximum=0), only OOP tracking
        if ("DED", "INDV", "INN") in acc_map:
            ded = acc_map[("DED", "INDV", "INN")]
            assert float(ded["maximum"]) == 0.00

        # Should have OOP tracking
        assert ("OOP", "INDV", "INN") in acc_map
        oop = acc_map[("OOP", "INDV", "INN")]
        assert float(oop["maximum"]) == 4500.00

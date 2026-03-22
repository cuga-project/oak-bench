"""
Tests for Benefits-related endpoints:
- POST /search_benefits
- POST /get_benefit_details
"""

import pytest


class TestSearchBenefits:
    """Tests for POST /search_benefits endpoint."""

    def test_office_visit_search(self, client, basic_request_body, john_contract_uid):
        """Test Case 1: Search for office visit benefits."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "office visit",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "benefitResults" in data
        assert len(data["benefitResults"]) > 0

        result = data["benefitResults"][0]
        assert "context" in result
        assert "categories" in result

        # Verify inquiry
        assert "office visit" in result["context"]["searchQuery"].lower()

        # Check service categories
        assert len(result["categories"]) > 0
        service_cat = result["categories"][0]
        assert "planType" in service_cat
        assert "categories" in service_cat

        # Find office visit benefits
        found_pcp = False
        found_specialist = False

        for category in service_cat["categories"]:
            for service in category["services"]:
                for benefit in service["benefits"]:
                    if "PCP" in benefit["specificationName"]:
                        found_pcp = True
                        # Check PCP copay
                        for scenario in benefit["scenarios"]:
                            for network in scenario["networks"]:
                                if network["networkCode"] == "INN":
                                    copays = [
                                        cs
                                        for cs in network["costComponents"]
                                        if cs["type"] == "Copayment"
                                    ]
                                    assert len(copays) > 0
                                    assert "$25" in copays[0]["value"]

                    if "Specialist" in benefit["specificationName"]:
                        found_specialist = True
                        # Check specialist copay
                        for scenario in benefit["scenarios"]:
                            for network in scenario["networks"]:
                                if network["networkCode"] == "INN":
                                    copays = [
                                        cs
                                        for cs in network["costComponents"]
                                        if cs["type"] == "Copayment"
                                    ]
                                    assert len(copays) > 0
                                    assert "$55" in copays[0]["value"]

        assert found_pcp, "PCP office visit benefit not found"
        assert found_specialist, "Specialist office visit benefit not found"

    def test_mri_search(self, client, basic_request_body, john_contract_uid):
        """Test Case 2: Search for MRI benefits."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "mri",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        result = data["benefitResults"][0]
        assert "mri" in result["context"]["searchQuery"].lower()

        # Check for associated treatments
        if result.get("relatedProcedures"):
            assert len(result["relatedProcedures"]) > 0
            treatment = result["relatedProcedures"][0]
            assert "code" in treatment
            assert "name" in treatment
            assert "CPT:70551" in treatment["code"]

        # Find MRI benefit
        found_mri = False
        for category in result["categories"][0]["categories"]:
            for service in category["services"]:
                for benefit in service["benefits"]:
                    if "MRI" in benefit["specificationName"]:
                        found_mri = True

                        # Check INN network
                        for scenario in benefit["scenarios"]:
                            inn_network = None
                            oon_network = None

                            for network in scenario["networks"]:
                                if network["networkCode"] == "INN":
                                    inn_network = network
                                elif network["networkCode"] == "OON":
                                    oon_network = network

                            # INN: 20% coinsurance, precert required
                            if inn_network:
                                assert inn_network["deductibleRequired"] == "Yes"
                                assert inn_network["priorAuthRequired"] == "Y"
                                coins = [
                                    cs
                                    for cs in inn_network["costComponents"]
                                    if cs["type"] == "Coinsurance"
                                ]
                                assert len(coins) > 0
                                assert "20%" in coins[0]["value"]

                            # OON: 40% coinsurance
                            if oon_network:
                                coins = [
                                    cs
                                    for cs in oon_network["costComponents"]
                                    if cs["type"] == "Coinsurance"
                                ]
                                assert len(coins) > 0
                                assert "40%" in coins[0]["value"]

        assert found_mri, "MRI benefit not found"

    def test_unsupported_inquiry(self, client, basic_request_body, john_contract_uid):
        """Test Case 3: Unsupported inquiry returns error with supported list."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "dental cleaning",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 400
        error = response.json()
        assert "detail" in error

        # Should include supported keywords
        if isinstance(error["detail"], dict):
            assert "supported" in error["detail"]
            assert len(error["detail"]["supported"]) > 0

    def test_knee_injury_search(self, client, basic_request_body, john_contract_uid):
        """Test Case 4: Search for knee injury (emergency) benefits."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "knee injury",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        result = data["benefitResults"][0]

        # Should return emergency room benefit
        found_er = False
        for category in result["categories"][0]["categories"]:
            for service in category["services"]:
                for benefit in service["benefits"]:
                    if "Emergency" in benefit["specificationName"]:
                        found_er = True

                        # Check copay
                        for scenario in benefit["scenarios"]:
                            for network in scenario["networks"]:
                                if network["networkCode"] == "INN":
                                    copays = [
                                        cs
                                        for cs in network["costComponents"]
                                        if cs["type"] == "Copayment"
                                    ]
                                    assert len(copays) > 0
                                    assert "$400" in copays[0]["value"]

        assert found_er, "Emergency room benefit not found"

    def test_knee_surgery_search(self, client, basic_request_body, john_contract_uid):
        """Test Case 5: Search for knee surgery benefits."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "knee surgery",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        result = data["benefitResults"][0]
        assert "knee surgery" in result["context"]["searchQuery"].lower()

        # Check for associated treatments
        if result.get("relatedProcedures"):
            treatment = result["relatedProcedures"][0]
            assert "CPT:29881" in treatment["code"]

    def test_invalid_contract(self, client, basic_request_body):
        """Test Case 6: Invalid contract UID returns error."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "office visit",
                "contract_uid": "INVALID-CONTRACT-UID",
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code in [403, 404]

    def test_effective_date_format(self, client, basic_request_body, john_contract_uid):
        """Test Case 7: Effective date is formatted as MMDDYYYY."""
        response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "office visit",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        result = data["benefitResults"][0]
        # effectiveDate should be in MMDDYYYY format
        assert len(result["context"]["effectiveDate"]) == 8
        assert result["context"]["effectiveDate"] == "01012025"


class TestGetBenefitDetails:
    """Tests for POST /get_benefit_details endpoint."""

    def test_emergency_room_details(
        self, client, basic_request_body, john_contract_uid
    ):
        """Test Case 1: Get detailed ER benefit information."""
        # First, get the doc_id and benefit_sys_id from search
        search_response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "knee injury",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert search_response.status_code == 200
        search_data = search_response.json()
        result = search_data["benefitResults"][0]
        doc_id = result["context"]["documentId"]

        # Find ER benefit sys ID
        benefit_sys_id = None
        for category in result["categories"][0]["categories"]:
            for service in category["services"]:
                for benefit in service["benefits"]:
                    if "Emergency" in benefit["specificationName"]:
                        benefit_sys_id = benefit["systemIdentifier"]
                        break

        assert benefit_sys_id is not None

        # Now get details
        response = client.post(
            "/get_benefit_details",
            json=basic_request_body,
            params={
                "contract_uid": john_contract_uid,
                "doc_id": doc_id,
                "benefit_sys_id": benefit_sys_id,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "benefitResults" in data
        assert len(data["benefitResults"]) > 0

        detail_result = data["benefitResults"][0]
        assert "mcid" in detail_result
        assert "contractUID" in detail_result
        assert "benefitSysId" in detail_result
        assert "serviceCategory" in detail_result
        assert "planLevel" in detail_result

        # Check service category details
        service_cat = detail_result["serviceCategory"][0]
        assert "services" in service_cat

        service_group = service_cat["services"][0]
        assert "service" in service_group

        service_detail = service_group["service"][0]
        assert "situations" in service_detail

        # Check for diagnosis codes
        situation = service_detail["situations"][0]
        assert "diagnosisCd" in situation
        assert len(situation["diagnosisCd"]) > 0

        # Check networks
        assert "networks" in situation
        inn_network = None
        for network in situation["networks"]:
            if network["code"] == "INN":
                inn_network = network
                break

        assert inn_network is not None
        assert "costshares" in inn_network

    def test_doc_id_mismatch(self, client, basic_request_body, john_contract_uid):
        """Test Case 2: Wrong doc_id returns error."""
        response = client.post(
            "/get_benefit_details",
            json=basic_request_body,
            params={
                "contract_uid": john_contract_uid,
                "doc_id": "WRONG-DOC-ID",
                "benefit_sys_id": "82da10ab-c05d-46e1-bf48-ad61ea70eb3d",
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 400
        assert "mismatch" in response.json()["detail"].lower()

    def test_invalid_benefit_sys_id(
        self, client, basic_request_body, john_contract_uid
    ):
        """Test Case 3: Invalid benefit sys ID returns 404."""
        # Get valid doc_id first
        search_response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "office visit",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        doc_id = search_response.json()["benefitResults"][0]["context"]["documentId"]

        response = client.post(
            "/get_benefit_details",
            json=basic_request_body,
            params={
                "contract_uid": john_contract_uid,
                "doc_id": doc_id,
                "benefit_sys_id": "INVALID-BENEFIT-SYS-ID",
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 404

    def test_plan_level_benefits(self, client, basic_request_body, john_contract_uid):
        """Test Case 4: Plan level benefits are included."""
        # Get office visit details
        search_response = client.post(
            "/search_benefits",
            json=basic_request_body,
            params={
                "inquiry_keyword": "office visit",
                "contract_uid": john_contract_uid,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        result = search_response.json()["benefitResults"][0]
        doc_id = result["context"]["documentId"]

        # Find PCP benefit
        benefit_sys_id = None
        for category in result["categories"][0]["categories"]:
            for service in category["services"]:
                for benefit in service["benefits"]:
                    if "PCP" in benefit["specificationName"]:
                        benefit_sys_id = benefit["systemIdentifier"]
                        break

        response = client.post(
            "/get_benefit_details",
            json=basic_request_body,
            params={
                "contract_uid": john_contract_uid,
                "doc_id": doc_id,
                "benefit_sys_id": benefit_sys_id,
                "coverage_start_dt": "2025-01-01",
                "coverage_end_dt": "2025-12-31",
            },
        )

        assert response.status_code == 200
        data = response.json()

        detail_result = data["benefitResults"][0]

        # Check plan level
        assert "planLevel" in detail_result
        assert len(detail_result["planLevel"]) > 0

        plan_level = detail_result["planLevel"][0]
        assert "planType" in plan_level
        assert "benefits" in plan_level

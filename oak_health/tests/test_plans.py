"""
Tests for Plans Catalog endpoints:
  GET /plans
  GET /plans/compare
  GET /plans/{plan_id}

Tests are organised into three difficulty tiers that mirror the evaluation
scenarios in PLANS_API_DESIGN.md:

  Easy   — single-endpoint catalog queries
  Medium — cross-API chains: plan catalog + member-specific endpoints
  Hard   — multi-hop reasoning chains that surface non-obvious traps
           (aggregate deductibles, HSA math, specialty-drug cost variance, etc.)
"""

import pytest
import sys
from pathlib import Path


from fastapi.testclient import TestClient
from oak_health.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def john_member_id():
    return "121231234"


@pytest.fixture
def jane_member_id():
    return "882771300"


@pytest.fixture
def john_coverage_key_2025():
    return "1J1U-20250101-20251231-MED-57AMFC"


@pytest.fixture
def john_contract_uid():
    return "CONTRACT-UID-JOHN-1001"


ALL_PLAN_IDS = [
    "OAK-PPO-PREMIER-2025",
    "OAK-PPO-STANDARD-2025",
    "OAK-HMO-CLASSIC-2025",
    "OAK-HDHP-2025",
    "OAK-EPO-SELECT-2025",
    "OAK-POS-FLEX-2025",
    "OAK-HMO-VALUE-2025",
]


# ===========================================================================
# EASY TESTS
# E1 — Plan lookup: list → detail
# E2 — Filter: HSA-eligible plans
# E3 — Compare two plans
# ===========================================================================


class TestEasy:
    """Single-endpoint catalog queries that require no cross-API chaining."""

    # --- E1: GET /plans returns all 7 plans ---

    def test_list_plans_returns_all(self, client):
        """GET /plans returns all 7 catalog plans."""
        resp = client.get("/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalCount"] == 7
        assert len(data["plans"]) == 7

    def test_list_plans_structure(self, client):
        """Each plan summary has required fields including bridge fields."""
        resp = client.get("/plans")
        assert resp.status_code == 200
        for plan in resp.json()["plans"]:
            assert "planId" in plan
            assert "planName" in plan
            assert "planType" in plan
            assert "estimatedMonthlyPremium" in plan
            assert "individual" in plan["estimatedMonthlyPremium"]
            assert "family" in plan["estimatedMonthlyPremium"]
            assert "features" in plan
            assert "planContractCode" in plan  # bridge field
            assert "networkBrandCode" in plan  # bridge field
            assert plan["networkBrandCode"] == "ACME"

    def test_list_plans_filter_by_type_ppo(self, client):
        """Filtering by planType=PPO returns only PPO plans."""
        resp = client.get("/plans?plan_type=PPO")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalCount"] == 2
        for p in data["plans"]:
            assert p["planType"] == "PPO"

    def test_list_plans_filter_by_type_hmo(self, client):
        """Filtering by planType=HMO returns HMO plans (Classic + Value)."""
        resp = client.get("/plans?plan_type=HMO")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalCount"] == 2
        for p in data["plans"]:
            assert p["planType"] == "HMO"

    def test_list_plans_filter_hsa_eligible(self, client):
        """Only the HDHP plan is HSA-eligible."""
        resp = client.get("/plans?hsa_eligible=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalCount"] == 1
        assert data["plans"][0]["planId"] == "OAK-HDHP-2025"
        assert data["plans"][0]["features"]["hsaEligible"] is True

    def test_list_plans_filter_max_premium(self, client):
        """max_premium=350 should return only plans at or below $350/month."""
        resp = client.get("/plans?max_premium=350")
        assert resp.status_code == 200
        data = resp.json()
        # HDHP ($280), Value HMO ($200), Classic HMO ($350)
        assert data["totalCount"] == 3
        for p in data["plans"]:
            raw = (
                p["estimatedMonthlyPremium"]["individual"]
                .replace("$", "")
                .replace(",", "")
            )
            assert float(raw) <= 350

    def test_list_plans_filter_no_oon(self, client):
        """Plans with no OON coverage (HMO and EPO types)."""
        resp = client.get("/plans")
        data = resp.json()
        no_oon = [p for p in data["plans"] if not p["features"]["outOfNetworkCoverage"]]
        # Classic HMO, EPO Select, Value HMO = 3 plans
        assert len(no_oon) == 3

    # --- E1 cont.: GET /plans/{plan_id} ---

    def test_get_plan_detail_premier(self, client):
        """GET /plans/OAK-PPO-PREMIER-2025 returns full detail."""
        resp = client.get("/plans/OAK-PPO-PREMIER-2025")
        assert resp.status_code == 200
        plan = resp.json()["plan"]
        assert plan["planId"] == "OAK-PPO-PREMIER-2025"
        assert plan["planType"] == "PPO"
        assert plan["deductibleType"] == "embedded"
        assert "innCoverage" in plan
        assert "oonCoverage" in plan
        assert plan["oonCoverage"] is not None  # PPO has OON
        assert "drugCoverage" in plan
        assert "specialBenefits" in plan
        assert "bestFor" in plan

    def test_get_plan_detail_hmo_no_oon(self, client):
        """HMO plans have oonCoverage=null."""
        for plan_id in [
            "OAK-HMO-CLASSIC-2025",
            "OAK-HMO-VALUE-2025",
            "OAK-EPO-SELECT-2025",
        ]:
            resp = client.get(f"/plans/{plan_id}")
            assert resp.status_code == 200
            plan = resp.json()["plan"]
            assert plan["oonCoverage"] is None, f"{plan_id} should have no OON coverage"

    def test_get_plan_detail_hdhp_aggregate_deductible(self, client):
        """HDHP plan has aggregate deductible type."""
        resp = client.get("/plans/OAK-HDHP-2025")
        assert resp.status_code == 200
        plan = resp.json()["plan"]
        assert plan["deductibleType"] == "aggregate"
        assert plan["features"]["hsaEligible"] is True
        assert plan["features"]["fsaEligible"] is False  # cannot combine HSA + FSA

    def test_get_plan_not_found(self, client):
        """GET /plans/{bad_id} returns 404."""
        resp = client.get("/plans/OAK-DOES-NOT-EXIST")
        assert resp.status_code == 404

    # --- E2: HSA-eligible filter already covered above ---

    # --- E3: GET /plans/compare ---

    def test_compare_two_plans(self, client):
        """Compare Premier PPO vs HDHP returns both plans with comparisonDimensions."""
        resp = client.get("/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-HDHP-2025")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["plans"]) == 2
        assert len(data["comparisonDimensions"]) > 0
        plan_ids = {p["planId"] for p in data["plans"]}
        assert "OAK-PPO-PREMIER-2025" in plan_ids
        assert "OAK-HDHP-2025" in plan_ids

    def test_compare_three_plans(self, client):
        """Compare 3 plans returns all 3 with full PlanDetail."""
        resp = client.get(
            "/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-HMO-VALUE-2025,OAK-HDHP-2025"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["plans"]) == 3
        # All plans have full detail fields
        for plan in data["plans"]:
            assert "innCoverage" in plan
            assert "drugCoverage" in plan
            assert "deductibleType" in plan

    def test_compare_requires_two_minimum(self, client):
        """Providing only one plan ID returns 400."""
        resp = client.get("/plans/compare?ids=OAK-PPO-PREMIER-2025")
        assert resp.status_code == 400

    def test_compare_max_four_plans(self, client):
        """Providing 5 plan IDs returns 400."""
        ids = ",".join(ALL_PLAN_IDS[:5])
        resp = client.get(f"/plans/compare?ids={ids}")
        assert resp.status_code == 400

    def test_compare_invalid_plan_id(self, client):
        """Any non-existent plan ID returns 404."""
        resp = client.get("/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-FAKE-PLAN")
        assert resp.status_code == 404

    def test_compare_route_not_treated_as_plan_id(self, client):
        """'compare' must NOT be matched as a plan_id — routing order check."""
        # If routing is wrong, this would hit GET /plans/{plan_id} with "compare"
        # and return 404 with "Plan 'compare' not found".
        # Correct behavior: 400 (no ids param provided).
        resp = client.get("/plans/compare")
        # No 'ids' query param → FastAPI validation error (422) or 400 from our handler
        assert resp.status_code in (400, 422)

    def test_compare_compares_premiums(self, client):
        """Premier PPO premium ($650) > Value HMO premium ($200)."""
        resp = client.get("/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-HMO-VALUE-2025")
        data = resp.json()
        premiums = {
            p["planId"]: float(
                p["estimatedMonthlyPremium"]["individual"]
                .replace("$", "")
                .replace(",", "")
            )
            for p in data["plans"]
        }
        assert premiums["OAK-PPO-PREMIER-2025"] > premiums["OAK-HMO-VALUE-2025"]

    def test_compare_dimensions_present(self, client):
        """comparisonDimensions includes the most important comparison keys."""
        resp = client.get("/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-HDHP-2025")
        dims = resp.json()["comparisonDimensions"]
        assert "features.hsaEligible" in dims
        assert "features.outOfNetworkCoverage" in dims
        assert "deductibleType" in dims
        assert "drugCoverage.tier4Specialty" in dims


# ===========================================================================
# MEDIUM TESTS
# M1 — Plan catalog + member coverage: "my plan vs alternatives"
# M2 — Plan detail contains benefit info (no need to chain search_benefits)
# M3 — Plan network bridge to find_care_specialty
# M4 — Deductible accumulator + plan catalog: "is switching worth it?"
# ===========================================================================


class TestMedium:
    """Cross-API chains combining plan catalog with member-specific endpoints."""

    def test_m1_member_plan_vs_catalog(self, client, john_member_id):
        """
        M1: Agent chain — get member's current plan → compare against catalog.
        John's coverage_key encodes PPO. We can then look up catalog PPO plans
        and compare OOP max values.
        """
        # Step 1: get member coverage to learn their plan type
        coverage_resp = client.post(
            "/get_coverage_period", json={"memberId": john_member_id}
        )
        assert coverage_resp.status_code == 200
        periods = coverage_resp.json()["eligibility"][0]["periods"]
        active = next(p for p in periods if p["status"]["identifier"] == "A")
        # John's active plan is a PPO (arrangement identifier == "PPO")
        assert active["arrangement"]["identifier"] == "PPO"

        # Step 2: list catalog PPO plans
        plans_resp = client.get("/plans?plan_type=PPO")
        assert plans_resp.status_code == 200
        ppo_plans = plans_resp.json()["plans"]
        assert len(ppo_plans) == 2

        # Step 3: compare the two PPO options
        compare_resp = client.get(
            "/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-PPO-STANDARD-2025"
        )
        assert compare_resp.status_code == 200
        comparison = compare_resp.json()
        oops = {
            p["planId"]: p["innCoverage"]["individualOopMax"]
            for p in comparison["plans"]
        }

        # Premier PPO has lower OOP max than Standard PPO
        def _dollars(s: str) -> float:
            return float(s.replace("$", "").replace(",", "").split()[0])

        assert _dollars(oops["OAK-PPO-PREMIER-2025"]) < _dollars(
            oops["OAK-PPO-STANDARD-2025"]
        )

    def test_m2_plan_benefit_info_embedded(self, client):
        """
        M2: Plan detail contains full benefit cost info directly — no need to
        call search_benefits separately. Verify MRI (imaging) cost is accessible.
        """
        resp = client.get("/plans/OAK-PPO-STANDARD-2025")
        assert resp.status_code == 200
        plan = resp.json()["plan"]
        # Imaging is part of innCoverage — agent can answer "what does Standard PPO
        # cover for MRI?" directly from this response
        assert "imaging" in plan["innCoverage"]
        assert plan["innCoverage"]["imaging"] != ""
        # OON imaging is also available
        assert "imaging" in plan["oonCoverage"]

    def test_m2_drug_tier_info_accessible(self, client):
        """
        M2 variant: Drug tier coinsurance is accessible per plan.
        Agent can answer "would Humira (tier 4 specialty) be covered on HDHP?"
        """
        resp = client.get("/plans/OAK-HDHP-2025")
        assert resp.status_code == 200
        plan = resp.json()["plan"]
        # Tier 4 specialty is present and non-empty
        assert plan["drugCoverage"]["tier4Specialty"] != ""
        # HDHP requires deductible first for drugs
        assert "deductible" in plan["drugCoverage"]["tier4Specialty"].lower()

    def test_m3_plan_bridge_field_for_find_care(self, client, john_member_id):
        """
        M3: Use plan's networkBrandCode to call find_care_specialty.
        Premier PPO network brand is ACME — same as John's coverage.
        """
        # Get Premier plan to extract brand code
        plan_resp = client.get("/plans/OAK-PPO-PREMIER-2025")
        assert plan_resp.status_code == 200
        brand_code = plan_resp.json()["plan"]["networkBrandCode"]
        assert brand_code == "ACME"

        # Use brand_code + john's contract_uid to find PCP providers
        find_resp = client.post(
            "/find_care_specialty"
            "?contract_uid=CONTRACT-UID-JOHN-1001"
            f"&brand_code={brand_code}"
            "&specialty_category_codes=25"
            "&stateCode=NY&zipCode=11211",
            json={"memberId": john_member_id},
        )
        assert find_resp.status_code == 200
        providers = find_resp.json()["providers"]
        assert len(providers) > 0

    def test_m4_accumulator_vs_plan_deductible(
        self, client, john_member_id, john_coverage_key_2025
    ):
        """
        M4: Compare John's current deductible progress against a potential new plan.
        John has met $250 of his $1,000 INN deductible (from accumulators).
        If he switched to Premier PPO ($500 deductible), he'd start over at $0.
        """
        # Step 1: get John's current accumulators
        acc_resp = client.post(
            "/get_benefit_accumulators",
            params={"coverage_key": john_coverage_key_2025},
            json={"memberId": john_member_id},
        )
        assert acc_resp.status_code == 200
        tracking = acc_resp.json()["tracking"]
        ind_ded = next(
            t
            for t in tracking
            if t["category"] == "DED" and t["scope"] == "INDV" and t["tier"] == "INN"
        )
        accumulated = float(ind_ded["accumulated"])  # 250.00
        current_max = float(ind_ded["maximum"])  # 1000.00
        remaining = current_max - accumulated  # 750.00
        assert remaining > 0  # still has deductible to meet

        # Step 2: check Premier PPO deductible — if switching, resets to $0
        plan_resp = client.get("/plans/OAK-PPO-PREMIER-2025")
        assert plan_resp.status_code == 200
        new_ded_str = plan_resp.json()["plan"]["innCoverage"]["individualDeductible"]
        new_ded = float(new_ded_str.replace("$", "").replace(",", ""))  # 500.00
        # Premier deductible ($500) < current plan max ($1,000) —
        # but John has ALREADY met $250, leaving only $750 on current plan.
        # Switching resets to $500 — a loss of the $250 already counted.
        assert new_ded < current_max
        assert accumulated > 0  # progress that would be lost on switch

    def test_m4_plan_type_referral_requirement(self, client):
        """
        M4 variant: Agent must know which plans require referrals before recommending.
        EPO does NOT require referrals; HMO does.
        """
        epo_resp = client.get("/plans/OAK-EPO-SELECT-2025")
        hmo_resp = client.get("/plans/OAK-HMO-CLASSIC-2025")

        epo = epo_resp.json()["plan"]
        hmo = hmo_resp.json()["plan"]

        assert epo["features"]["referralRequired"] is False
        assert hmo["features"]["referralRequired"] is True

        # Both lack OON coverage — but EPO has no referral burden
        assert epo["features"]["outOfNetworkCoverage"] is False
        assert hmo["features"]["outOfNetworkCoverage"] is False


# ===========================================================================
# HARD TESTS
# H1 — Specialty drug annual cost projection across plans
# H2 — Family aggregate deductible trap
# H3 — OON travel scenario: HMO vs PPO for traveler
# H4 — HSA math: HDHP true cost when HSA is factored in
# ===========================================================================


class TestHard:
    """
    Multi-hop reasoning chains that surface non-obvious traps in plan design.
    These tests verify that the DATA exposes the right signals for an agent
    to reason correctly — not that the agent itself reasons correctly.
    """

    def test_h1_specialty_drug_tier_variance(self, client):
        """
        H1: Specialty drug (tier 4) coinsurance varies meaningfully across plans.
        An agent calculating annual Humira cost (~$6,000/month list price) must
        know each plan's tier-4 rate to project real cost differences.

        Verify: tier4Specialty rates differ across plans AND all plans cover tier 4.
        """
        resp = client.get("/plans")
        assert resp.status_code == 200
        plan_ids = [p["planId"] for p in resp.json()["plans"]]

        tier4_rates = {}
        for pid in plan_ids:
            detail_resp = client.get(f"/plans/{pid}")
            assert detail_resp.status_code == 200
            plan = detail_resp.json()["plan"]
            tier4_rates[pid] = plan["drugCoverage"]["tier4Specialty"]

        # All plans must have a tier 4 rate (no plan silently excludes specialty drugs)
        for pid, rate in tier4_rates.items():
            assert rate, f"{pid} missing tier4Specialty"

        # Rates must NOT all be identical — variance is the point
        unique_rates = set(tier4_rates.values())
        assert len(unique_rates) > 1, (
            "All plans have identical tier4 rates — variance expected"
        )

        # Premier PPO tier 4 (20%) should be lower than Value HMO (30%)
        assert "20%" in tier4_rates["OAK-PPO-PREMIER-2025"]
        assert "30%" in tier4_rates["OAK-HMO-VALUE-2025"]

    def test_h1_annual_cost_calc_data_available(self, client):
        """
        H1 cont.: Annual cost = (monthly_premium × 12) + drug_cost_per_year.
        Both data points are accessible from a single GET /plans/{plan_id}.
        """
        resp = client.get("/plans/OAK-HDHP-2025")
        plan = resp.json()["plan"]
        # Premium is accessible
        individual_premium_str = plan["estimatedMonthlyPremium"]["individual"]
        assert individual_premium_str.startswith("$")
        # Tier 4 coinsurance is accessible
        t4 = plan["drugCoverage"]["tier4Specialty"]
        assert "%" in t4 or "coinsurance" in t4.lower()
        # OOP max caps the worst-case drug spend
        oop_max_str = plan["innCoverage"]["individualOopMax"]
        assert oop_max_str.startswith("$")

    def test_h2_aggregate_deductible_trap(self, client):
        """
        H2: Aggregate vs embedded deductible is THE key trap for families.
        HDHP and Value HMO use aggregate — family members cannot individually
        trigger coverage until the FULL family deductible is met.
        """
        compare_resp = client.get(
            "/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-HDHP-2025,OAK-HMO-VALUE-2025"
        )
        assert compare_resp.status_code == 200
        plans = {p["planId"]: p for p in compare_resp.json()["plans"]}

        # Premier PPO: embedded
        assert plans["OAK-PPO-PREMIER-2025"]["deductibleType"] == "embedded"
        # HDHP: aggregate (the trap)
        assert plans["OAK-HDHP-2025"]["deductibleType"] == "aggregate"
        # Value HMO: aggregate (the trap)
        assert plans["OAK-HMO-VALUE-2025"]["deductibleType"] == "aggregate"

        # The aggregate nature must be described in the family deductible field
        hdhp_fam_ded = plans["OAK-HDHP-2025"]["innCoverage"]["familyDeductible"]
        assert "aggregate" in hdhp_fam_ded.lower()

        value_fam_ded = plans["OAK-HMO-VALUE-2025"]["innCoverage"]["familyDeductible"]
        assert "aggregate" in value_fam_ded.lower()

    def test_h2_family_deductible_amounts(self, client):
        """
        H2 cont.: HDHP family deductible ($3,200 aggregate) looks cheaper than
        Premier PPO ($1,000 embedded) — but aggregate means one child could
        exhaust the whole limit. Verify both amounts are in the data.
        """
        premier = client.get("/plans/OAK-PPO-PREMIER-2025").json()["plan"]
        hdhp = client.get("/plans/OAK-HDHP-2025").json()["plan"]

        def _parse(s: str) -> float:
            return float(s.replace("$", "").replace(",", "").split()[0])

        premier_fam_ded = _parse(premier["innCoverage"]["familyDeductible"])
        hdhp_fam_ded = _parse(hdhp["innCoverage"]["familyDeductible"])

        # HDHP family deductible is numerically higher than Premier's
        assert hdhp_fam_ded > premier_fam_ded

    def test_h3_oon_travel_scenario(self, client):
        """
        H3: A member who travels must avoid HMO/EPO plans (zero OON coverage).
        For OON access, only PPO and POS plans qualify.
        An agent must identify which plans have OON coverage from the catalog.
        """
        resp = client.get("/plans")
        plans = resp.json()["plans"]

        oon_plans = [p for p in plans if p["features"]["outOfNetworkCoverage"]]
        no_oon_plans = [p for p in plans if not p["features"]["outOfNetworkCoverage"]]

        # Plans WITH OON: Premier PPO, Standard PPO, HDHP, POS Flex = 4
        assert len(oon_plans) == 4
        oon_ids = {p["planId"] for p in oon_plans}
        assert "OAK-PPO-PREMIER-2025" in oon_ids
        assert "OAK-PPO-STANDARD-2025" in oon_ids
        assert "OAK-HDHP-2025" in oon_ids
        assert "OAK-POS-FLEX-2025" in oon_ids

        # Plans WITHOUT OON: Classic HMO, EPO Select, Value HMO = 3
        assert len(no_oon_plans) == 3
        no_oon_ids = {p["planId"] for p in no_oon_plans}
        assert "OAK-HMO-CLASSIC-2025" in no_oon_ids
        assert "OAK-EPO-SELECT-2025" in no_oon_ids
        assert "OAK-HMO-VALUE-2025" in no_oon_ids

    def test_h3_oon_coinsurance_variance(self, client):
        """
        H3 cont.: OON coinsurance rates differ across plans with OON coverage.
        Premier (50%) vs POS (30%) vs Standard (40%) — agent must identify cheapest OON.
        """
        compare_resp = client.get(
            "/plans/compare?ids=OAK-PPO-PREMIER-2025,OAK-PPO-STANDARD-2025,OAK-POS-FLEX-2025"
        )
        plans = {p["planId"]: p for p in compare_resp.json()["plans"]}

        # All three have OON coverage
        for pid in plans:
            assert plans[pid]["oonCoverage"] is not None
            assert plans[pid]["features"]["outOfNetworkCoverage"] is True

        # POS OON specialist copay mentions 30%
        pos_oon_spec = plans["OAK-POS-FLEX-2025"]["oonCoverage"]["specialistCopay"]
        assert "30%" in pos_oon_spec

        # Premier OON specialist copay mentions 50%
        premier_oon_spec = plans["OAK-PPO-PREMIER-2025"]["oonCoverage"][
            "specialistCopay"
        ]
        assert "50%" in premier_oon_spec

    def test_h4_hsa_eligibility_only_hdhp(self, client):
        """
        H4: HSA eligibility is exclusively on the HDHP plan.
        An agent advising on tax savings must identify HDHP as the only HSA option.
        """
        resp = client.get("/plans")
        plans = resp.json()["plans"]
        hsa_plans = [p for p in plans if p["features"]["hsaEligible"]]
        non_hsa_plans = [p for p in plans if not p["features"]["hsaEligible"]]

        assert len(hsa_plans) == 1
        assert hsa_plans[0]["planId"] == "OAK-HDHP-2025"
        assert len(non_hsa_plans) == 6

        # FSA is NOT available on HDHP (cannot combine HSA + FSA)
        hdhp_detail = client.get("/plans/OAK-HDHP-2025").json()["plan"]
        assert hdhp_detail["features"]["fsaEligible"] is False
        assert hdhp_detail["features"]["hsaEligible"] is True

    def test_h4_hsa_info_in_highlights(self, client):
        """
        H4 cont.: HDHP highlights must mention HSA contribution limit so an agent
        can factor it into annual cost calculations.
        """
        resp = client.get("/plans/OAK-HDHP-2025")
        plan = resp.json()["plan"]
        highlights_text = " ".join(plan["highlights"]).lower()
        # Must mention HSA
        assert "hsa" in highlights_text
        # Must mention the tax benefit concept
        assert "pre-tax" in highlights_text or "tax" in highlights_text

    def test_h4_hdhp_preventive_care_free(self, client):
        """
        H4 cont.: On HDHP, preventive care is $0 even before deductible.
        This is a critical nuance — ACA requires it. The data must reflect this.
        """
        resp = client.get("/plans/OAK-HDHP-2025")
        plan = resp.json()["plan"]
        preventive = plan["innCoverage"]["preventiveCare"]
        assert "$0" in preventive or "free" in preventive.lower()
        assert "deductible" in preventive.lower() or "aca" in preventive.lower()

    def test_h4_hdhp_telehealth_pre_deductible(self, client):
        """
        H4 cont.: HDHP telehealth is $0 pre-deductible — a meaningful benefit
        for someone who hasn't met their high deductible yet.
        """
        resp = client.get("/plans/OAK-HDHP-2025")
        plan = resp.json()["plan"]
        telehealth_copay = plan["specialBenefits"]["telehealthCopay"]
        assert "$0" in telehealth_copay
        # Must note pre-deductible eligibility
        assert (
            "pre-deductible" in telehealth_copay.lower()
            or "deductible" in telehealth_copay.lower()
        )

    def test_h_all_plans_have_complete_cost_structure(self, client):
        """
        Smoke test: every plan exposes the full cost structure an agent needs
        for multi-plan cost comparisons. No plan is missing critical fields.
        """
        for pid in ALL_PLAN_IDS:
            resp = client.get(f"/plans/{pid}")
            assert resp.status_code == 200
            plan = resp.json()["plan"]

            # Required top-level fields
            for field in [
                "planId",
                "planType",
                "deductibleType",
                "innCoverage",
                "drugCoverage",
                "specialBenefits",
                "features",
                "estimatedMonthlyPremium",
                "bestFor",
                "highlights",
            ]:
                assert field in plan, f"{pid} missing {field}"

            # INN cost structure completeness
            inn = plan["innCoverage"]
            for cost_field in [
                "individualDeductible",
                "familyDeductible",
                "individualOopMax",
                "familyOopMax",
                "primaryCareCopay",
                "specialistCopay",
                "erCopay",
                "imaging",
                "mentalHealthOutpatient",
            ]:
                assert inn.get(cost_field), f"{pid}.innCoverage missing {cost_field}"

            # Drug tier completeness
            drugs = plan["drugCoverage"]
            for tier_field in [
                "tier1Generic",
                "tier2PreferredBrand",
                "tier3NonPreferredBrand",
                "tier4Specialty",
            ]:
                assert drugs.get(tier_field), f"{pid}.drugCoverage missing {tier_field}"

            # OON: plans with OON coverage must have oonCoverage object
            if plan["features"]["outOfNetworkCoverage"]:
                assert plan["oonCoverage"] is not None, (
                    f"{pid} claims OON coverage but oonCoverage is null"
                )
            else:
                assert plan["oonCoverage"] is None, (
                    f"{pid} claims no OON but oonCoverage is set"
                )

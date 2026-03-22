from typing import List, Optional, Literal
from copy import deepcopy
from datetime import datetime
from fastapi import FastAPI, Body, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from oak_health.models import (
    GetMemberClaimsRequest,
    ClaimsResponse,
    PageInfo,
    ServiceRecord,
    CoveragePeriodResponse,
    PlanInformationResponse,
    BenefitsSearchResponse,
    CoverageInquiryResult,
    BenefitsDetailsResponse,
    BenefitDetailsResult,
    FindCareSpecialtyResponse,
    CareProviderProfile,
    FindCareSuggestionsResponse,
    SuggestionItem,
    SuggestionCriteria,
    SuggestionLocationDetails,
    MedicalInformationResponse,
    MedicalArticle,
    ConsumerText,
    EobPdfResponse,
    EobPdfItem,
    BillingResponse,
    BillingItem,
    CreatePaymentIntentResponse,
    ConfirmPaymentIntentResponse,
    BenefitAccumulatorsResponse,
    AccumulatorEntry,
    MemberProfileResponse,
    MemberProfile,
    MemberPreferences,
    PlanSummary,
    PlanDetail,
    PlansListResponse,
    PlanDetailResponse,
    PlanCompareResponse,
)
from oak_health.data import (
    CLAIMS_DB,
    CLAIM_DETAILS_DB,
    ELIGIBILITY_DB,
    COVERAGE_KEY_INDEX,
    PLAN_INFO_DB,
    CONTRACT_UID_TO_CD,
    SUPPORTED_BENEFIT_INTENTS,
    BENEFIT_DETAILS_DB,
    CONTRACT_UID_TO_CD,
    PROVIDERS_DB,
    SUGGESTIONS_DB,
    MEDICAL_KB,
    BILLING_LEDGER,
    PAYMENT_INTENTS,
    ACCUMULATORS_DB,
    MEMBER_PREFERENCES,
    PLAN_CATALOG,
)

from uuid import uuid4


app = FastAPI(
    title="Oak Healthcare Insurance",
    version="1.3.0",
    description="""
A healthcare insurance app, providing support for claims, coverage, benefits, plans and general health information.

""",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== Utilities =====
SORT_FIELD_MAP = {
    "start_date": "timeline.serviceStart",
    "end_date": "timeline.serviceEnd",
    "receive_date": "timeline.received",
    "process_date": "timeline.processed",
}


def sort_claims(claims: List[ServiceRecord], sort_by: str) -> List[ServiceRecord]:
    field_path = SORT_FIELD_MAP.get(sort_by, "timeline.serviceStart")
    parts = field_path.split(".")

    def get_nested_attr(obj, path):
        for part in path:
            obj = getattr(obj, part)
        return obj

    return sorted(claims, key=lambda c: get_nested_attr(c, parts), reverse=True)


def _to_mmddyyyy(iso_date: str) -> str:
    # Input 'YYYY-MM-DD' -> 'MMDDYYYY'
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%m%d%Y")


def _build_doc_id(contract_cd: str, coverage_start_dt: str) -> str:
    # e.g., '281019533353-01012025' style. We'll synthesize deterministic docIDs
    # using YYMMDD + hash fragment of contract.
    mmddyyyy = datetime.strptime(coverage_start_dt, "%Y-%m-%d").strftime("%m%d%Y")
    return f"{abs(hash(contract_cd + mmddyyyy)) % 10**12:012d}-{mmddyyyy}"


def _find_member_elig(member_id: str) -> CoveragePeriodResponse:
    elig = ELIGIBILITY_DB.get(member_id)
    if not elig:
        raise HTTPException(
            status_code=404, detail="Eligibility not found for memberId"
        )
    return elig


def _validate_contract_and_coverage(
    elig: CoveragePeriodResponse, contract_uid: str, cov_start: str, cov_end: str
):
    # contract_uid must match an eligibility entry; coverage dates must match one of its coverage entries
    owner_entry = None
    for e in elig.eligibility:
        if e.identifiers.contractUniqueId == contract_uid:
            for c in e.periods:
                if c.dates.start == cov_start and (c.dates.end or "") == (
                    cov_end or ""
                ):
                    return e, c
            owner_entry = e  # found contract, but not dates
    if owner_entry:
        raise HTTPException(
            status_code=404, detail="Coverage dates not found for provided contract_uid"
        )
    raise HTTPException(status_code=404, detail="contract_uid not found for memberId")


@app.post("/get_member_claims", response_model=ClaimsResponse, tags=["Claims"])
def get_member_claims(
    payload: GetMemberClaimsRequest = Body(...),
    sort_by: Literal["start_date", "end_date", "process_date", "receive_date"] = Query(
        default="start_date"
    ),
    size: int = Query(default=5, ge=1, le=5),
    page_index: int = Query(default=0, ge=0),
):
    """
    Get claim summaries for a member.
    Retrieves paginated claims list with financial details, provider info, and claim status.
    Args:
        user_context (UserContext): User context containing member ID, location (stateCode + zipCode, NOT Needed for claims), and metadata (NOT Needed).
        sort_by (str, optional): The field to sort by. Options: "start_date" (claim start date), "end_date" (claim end date), "process_date" (claim process date), "receive_date" (claim receive date). Defaults to "start_date".
        size (int, optional): Number of claims to fetch. Defaults to 5.
        page_index (int, optional): Page index. Defaults to 0.
    Returns:
        ClaimsResponse: Paginated claims list with metadata and details including
        - identifiers.uniqueId: Unique claim identifier (use for get_claim_details)
        - identifiers.displayId: Human-readable claim ID
        - classification.status.identifier: Status code ("APRVD", "DND", "PEND", "PROC")
        - parties.subject: Member information (identity.primaryId, givenName, familyName, birthDate)
        - financial: Financial details (allocation.patientShare, payment.disbursed, etc.)
        - parties.servicingEntity: Provider who performed service
        - parties.billingEntity: Provider who billed for service
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    member_claims = [
        c for c in CLAIMS_DB if c.parties.subject.identity.primaryId == payload.memberId
    ]
    if not member_claims:
        member_claims = [
            c
            for c in CLAIMS_DB
            if c.parties.subject.identity.secondaryId == payload.memberId
        ]

    total = len(member_claims)
    member_claims = sort_claims(member_claims, sort_by)

    start = page_index * size
    end = start + size
    page_items = member_claims[start:end]

    total_pages = (total + size - 1) // size if size > 0 else 0
    metadata = {
        "page": PageInfo(
            size=size, totalElements=total, totalPages=total_pages, number=page_index
        ).model_dump()
    }
    return ClaimsResponse(metadata=metadata, claims=page_items)


@app.post("/get_claim_details", response_model=ClaimsResponse, tags=["Claims"])
def get_claim_details(
    claim_uid: str = Query(..., description="Unique claim identifier (clmUid)"),
    payload: GetMemberClaimsRequest = Body(...),
    user_role: Optional[str] = Query(default="MEMBER"),
    cdhp_carveout: Optional[Literal["y", "n", "Y", "N"]] = Query(default="n"),
):
    """Get detailed information for a specific claim."""
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    base_claim = next(
        (c for c in CLAIMS_DB if c.identifiers.uniqueId == claim_uid), None
    )
    if not base_claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if payload.memberId not in (
        base_claim.parties.subject.identity.primaryId,
        base_claim.parties.subject.identity.secondaryId,
    ):
        raise HTTPException(
            status_code=404, detail="Claim not found for provided memberId"
        )

    detailed = deepcopy(base_claim)
    detail_block = CLAIM_DETAILS_DB.get(claim_uid, {})
    detailed.lineItems = detail_block.get("serviceLines", None)
    detailed.explanations = detail_block.get("eobs", None)

    metadata = {
        "page": PageInfo(size=1, totalElements=1, totalPages=1, number=0).model_dump()
    }
    return ClaimsResponse(metadata=metadata, claims=[detailed])


@app.post(
    "/get_coverage_period", response_model=CoveragePeriodResponse, tags=["Coverage"]
)
def get_coverage_period(
    payload: GetMemberClaimsRequest = Body(...),
    user_role: Optional[str] = Query(default="MEMBER"),
):
    """
    Retrieve coverage period information for a member.
    Includes eligibility and plan data for active and past periods.
    Args:
        user_role (str, optional): User role. Defaults to "MEMBER".
    Returns:
        CoveragePeriodResponse: Contains eligibility array with:
        - identifiers.contractUniqueId: Contract unique identifier
        - periods: Array of enrollment periods, each with periodKey
        - periods[].periodKey: Coverage key (use for get_plan_information and get_benefit_accumulators)
        - periods[].productName: Plan name
        - periods[].enrollees: Array of enrolled members under this period
        - periods[].dates.start / periods[].dates.end: Coverage dates
        - periods[].status.identifier: Active/Inactive status ("A" = Active, "I" = Inactive)
        - brand.identifier: Brand code (use for find_care_suggestions and find_care_specialty)
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")
    return _find_member_elig(payload.memberId)


@app.post(
    "/get_plan_information", response_model=PlanInformationResponse, tags=["Coverage"]
)
def get_plan_information(
    coverage_key: str = Query(..., description="Coverage key from get_coverage_period"),
    payload: GetMemberClaimsRequest = Body(...),
    opted_plan_type: str = Query(default="MED"),
):
    """
    Get plan information for a member and coverage period.
    Includes cost-sharing, network structure, and benefit period details.
    Args:
        user_context (UserContext): User context containing member ID, location details, and metadata.
        coverage_key (str): The coverage key from get_coverage_period (e.g., "1J1U-20250101-20251231-MED-57AMFC").
        opted_plan_type (str, optional): Plan type. Defaults to "MED".
    Returns:
        PlanInformationResponse: Contains plan structure with:
        - contractCd: Contract code and state
        - marketSegment: Market type (Large Group, Individual, etc.)
        - benefitPeriod: How benefits reset (Calendar Year, etc.)
        - network: Array of network types with cost-sharing details
        - costShare: Deductibles, coinsurance, copays by coverage level
        - valueBasedProviderInfo: Value-based care program details
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    owner_mbr = COVERAGE_KEY_INDEX.get(coverage_key)
    if not owner_mbr:
        raise HTTPException(status_code=404, detail="Coverage key not found")

    owner_elig = ELIGIBILITY_DB.get(owner_mbr)
    if not owner_elig:
        raise HTTPException(status_code=404, detail="Coverage owner not found")

    owner_hcids = {e.identifiers.accountId for e in owner_elig.eligibility}
    if payload.memberId != owner_mbr and payload.memberId not in owner_hcids:
        raise HTTPException(
            status_code=403, detail="Coverage key does not belong to provided memberId"
        )

    plan = PLAN_INFO_DB.get((coverage_key, opted_plan_type))
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Plan information not found for provided coverage key/type",
        )
    return plan


@app.post("/search_benefits", response_model=BenefitsSearchResponse, tags=["Benefits"])
def search_benefits(
    inquiry_keyword: str = Query(
        ..., description='e.g., "knee injury", "office visit", "mri", "knee surgery"'
    ),
    contract_uid: str = Query(...),
    coverage_start_dt: str = Query(..., description="YYYY-MM-DD"),
    coverage_end_dt: str = Query(..., description="YYYY-MM-DD"),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Search benefits for a specific inquiry.
    Finds coverage and cost-sharing for procedures, services, and conditions.
    Args:
        user_context (UserContext): User context containing member ID, location details.
        inquiry_keyword (str): The benefit search keyword (e.g., "knee surgery", "MRI").
        contract_uid (str): Contract UID from coverage period.
        coverage_start_dt (str): Coverage start date (YYYY-MM-DD).
        coverage_end_dt (str): Coverage end date (YYYY-MM-DD).
    Returns:
        BenefitsSearchResponse: Contains benefitResults array with:
        - context.documentId: Document identifier (use as doc_id in get_benefit_details)
        - context.searchQuery: The processed search query
        - categories: Array of product categories (Medical, etc.) with nested benefits
        - categories[].categories[].services[].benefits[].systemIdentifier: Benefit system ID (use in get_benefit_details)
        - categories[].categories[].services[].benefits[].scenarios[].networks[].networkCode: "INN" or "OON"
        - categories[].categories[].services[].benefits[].scenarios[].networks[].costComponents[]: cost sharing
        - relatedProcedures: Related CPT codes and names
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    end_dt = datetime.strptime(coverage_end_dt, "%Y-%m-%d").date()
    # today = datetime.today().date()
    # if end_dt < today:
    #     raise HTTPException(status_code=400, detail="plan is not available")
    # Validate eligibility + contract + coverage dates
    elig = _find_member_elig(payload.memberId)
    elig_entry, cov_entry = _validate_contract_and_coverage(
        elig, contract_uid, coverage_start_dt, coverage_end_dt
    )

    # Map to supported intent
    normalized = inquiry_keyword.strip().lower()
    # Simple contains logic to map to supported keys
    if "knee" in normalized and "injur" in normalized:
        intent_key = "knee injury"
    elif "office" in normalized or "pcp" in normalized or "specialist" in normalized:
        intent_key = "office visit"
    elif "mri" in normalized:
        intent_key = "mri"
    elif "knee" in normalized and ("surgery" in normalized or "surg" in normalized):
        intent_key = "knee surgery"
    else:
        supported = list(SUPPORTED_BENEFIT_INTENTS.keys())
        raise HTTPException(
            status_code=400,
            detail={"message": "Unsupported inquiry_keyword", "supported": supported},
        )

    builder = SUPPORTED_BENEFIT_INTENTS[intent_key]

    # Determine contractCd from mapping
    contract_cd = CONTRACT_UID_TO_CD.get(contract_uid, "UNKNOWN")

    # Choose mcid as the subscriber on this coverage if possible; else first member
    subscriber = next(
        (m for m in cov_entry.enrollees if m.relationship.identifier == "SUBSCR"), None
    )
    mcid = (
        subscriber.personId
        if subscriber
        else (
            cov_entry.enrollees[0].personId if cov_entry.enrollees else payload.memberId
        )
    )

    effective_mmddyyyy = _to_mmddyyyy(coverage_start_dt)
    doc_id = _build_doc_id(contract_cd, coverage_start_dt)

    result: CoverageInquiryResult = builder(
        contract_uid, contract_cd, effective_mmddyyyy, doc_id, mcid
    )

    # Return the benefitResults array as required
    return BenefitsSearchResponse(benefitResults=[result])


@app.post(
    "/get_benefit_details", response_model=BenefitsDetailsResponse, tags=["Benefits"]
)
def get_benefit_details(
    contract_uid: str = Query(...),
    doc_id: str = Query(...),
    benefit_sys_id: str = Query(...),
    coverage_start_dt: str = Query(..., description="YYYY-MM-DD"),
    coverage_end_dt: str = Query(..., description="YYYY-MM-DD"),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Validates member + contract + coverage dates. Returns detailed benefit structure
    for the given benefit_sys_id. Verifies doc_id consistency with `coverage_start_dt`.
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Validate eligibility and coverage
    elig = _find_member_elig(payload.memberId)
    elig_entry, cov_entry = _validate_contract_and_coverage(
        elig, contract_uid, coverage_start_dt, coverage_end_dt
    )

    # Validate doc_id deterministic match with start date + contractCd
    contract_cd = CONTRACT_UID_TO_CD.get(contract_uid, "UNKNOWN")
    expected_doc_id = _build_doc_id(contract_cd, coverage_start_dt)
    if doc_id != expected_doc_id:
        raise HTTPException(
            status_code=400,
            detail=f"doc_id mismatch for coverage_start_dt; expected {expected_doc_id}",
        )

    # Find a subscriber to use as mcid when present
    subscriber = next(
        (m for m in cov_entry.enrollees if m.relationship.identifier == "SUBSCR"), None
    )
    mcid = subscriber.personId if subscriber else payload.memberId

    key = (contract_uid, benefit_sys_id)
    detail = BENEFIT_DETAILS_DB.get(key)
    if not detail:
        raise HTTPException(
            status_code=404, detail="Benefit details not found for given identifiers"
        )

    # Build result with appropriate effective date format
    effective_mmddyyyy = _to_mmddyyyy(coverage_start_dt)

    return BenefitsDetailsResponse(
        benefitResults=[
            BenefitDetailsResult(
                mcid=mcid,
                contractUID=contract_uid,
                effectiveDt=effective_mmddyyyy,
                benefitSysId=benefit_sys_id,
                serviceCategory=detail["serviceCategory"],
                planLevel=detail["planLevel"],
            )
        ]
    )


def _location_distance(
    req_state: str, req_zip: str, prov_state: str, prov_zip: str
) -> float:
    """Return a synthetic distance based on state/zip match.

    Same state + same zip  → 0.0 miles (very close)
    Same state, diff zip   → 15.0 miles (same region, different area)
    Different state        → 999.0 miles (out of range)
    """
    if req_state.upper() == prov_state.upper():
        return 0.0 if req_zip == prov_zip else 15.0
    return 999.0


@app.post(
    "/find_care_specialty", response_model=FindCareSpecialtyResponse, tags=["Find Care"]
)
def find_care_specialty(
    contract_uid: str = Query(...),
    brand_code: str = Query(...),
    specialty_category_codes: List[str] = Query(..., description="e.g., 25, 231, 75"),
    taxonomy_codes: Optional[List[str]] = Query(
        None, description="Optional taxonomy filters"
    ),
    distance: str = Query("20", description="Miles"),
    page_index: int = Query(0, ge=0, description="Zero-based page index"),
    size: int = Query(5, ge=1, le=5, description="Page size (max 5)"),
    stateCode: Optional[str] = Query(
        None,
        description="US state code (e.g. 'NY'). Use if location is not in request body.",
    ),
    zipCode: Optional[str] = Query(
        None,
        description="ZIP code (e.g. '11211'). Use if location is not in request body.",
    ),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Validates member & contract. Filters providers by specialty categories and location.
    Location is required via query params stateCode + zipCode.
    Returns providers with: name, address, expertise.specialtyCategories, network.status ("TP_INNETWORK"),
    network.accept_new_patients, address.coordinates.distanceMiles, address.contact.phone

    Distance rules:
    - Same state + same zip  → 0 miles (very close)
    - Same state, diff zip   → 15 miles (same region)
    - Different state        → 999 miles (out of range)
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Resolve location from query params only
    resolved_state = stateCode
    resolved_zip = zipCode

    if not resolved_state:
        raise HTTPException(status_code=400, detail="stateCode is required in location")

    # Validate contract belongs to the member (via eligibility)
    elig = _find_member_elig(payload.memberId)
    if all(e.identifiers.contractUniqueId != contract_uid for e in elig.eligibility):
        raise HTTPException(
            status_code=403, detail="contract_uid does not belong to provided memberId"
        )

    req_state = resolved_state
    req_zip = resolved_zip or ""

    try:
        max_miles = float(distance)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid distance value")

    # Prepare filters
    cat_set = set(specialty_category_codes)
    tax_set = set(taxonomy_codes) if taxonomy_codes else None

    matched: List[CareProviderProfile] = []
    for p in PROVIDERS_DB:
        # Category match
        if not (cat_set & set(p.expertise.specialtyCategories)):
            continue
        # Optional taxonomy match
        if tax_set:
            p_tax = {t.code for t in p.expertise.taxonomies}
            if not (p_tax & tax_set):
                continue
        # Distance filter using state/zip comparison
        prov_state = p.address.address.stateCode or ""
        prov_zip = p.address.address.zipCode or ""
        d = _location_distance(req_state, req_zip, prov_state, prov_zip)
        if d > max_miles:
            continue

        # Shallow copy with distance injected
        p_out = CareProviderProfile(**p.model_dump())
        p_out.address.coordinates.distanceMiles = round(d, 1)

        matched.append(p_out)

    start = page_index * size
    end = start + size
    page_items = matched[start:end]

    return FindCareSpecialtyResponse(providers=page_items)


@app.post(
    "/find_care_suggestions",
    response_model=FindCareSuggestionsResponse,
    tags=["Find Care"],
)
def find_care_suggestions(
    search_text: str = Query(
        ...,
        description='Free-text query, e.g., "primary care doctor", "mri", "knee surgery"',
    ),
    brand_code: str = Query(
        ..., description="Brand code from coverage period (e.g., ACME, VSTA)"
    ),
    stateCode: Optional[str] = Query(
        None,
        description="US state code (e.g. 'NY'). Use if location is not in request body.",
    ),
    zipCode: Optional[str] = Query(
        None,
        description="ZIP code (e.g. '11211'). Use if location is not in request body.",
    ),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Fetch care provider suggestions based on search criteria.
    Location is required via query params stateCode + zipCode.
    Returns suggestionList[].criteria.specialtyCategoryList[].identifier (use as specialty_category_codes)
    and suggestionList[].criteria.taxonomyList[].code (use as taxonomy_codes) for find_care_specialty.
    """
    # Resolve location from query params only
    resolved_state = stateCode
    resolved_zip = zipCode

    if not resolved_state:
        raise HTTPException(status_code=400, detail="stateCode is required in location")
    # Verify member eligibility exists (brand not enforced here; optional to add)
    _ = _find_member_elig(payload.memberId)

    norm = search_text.strip().lower()

    # Simple intent detection
    if any(
        k in norm
        for k in ["primary care", "pcp", "family doctor", "general practitioner"]
    ):
        intent = "SPECIALTY"
        key = "primary care"
    elif any(k in norm for k in ["radiology", "imaging"]):
        intent = "SPECIALTY"
        key = "radiology"
    elif "knee" in norm and "surg" in norm:
        intent = "PROCEDURE"
        key = "knee surgery"
    elif "mri" in norm:
        intent = "PROCEDURE"
        key = "mri"
    else:
        # Default to primary care specialty
        intent = "SPECIALTY"
        key = "primary care"

    base_list = SUGGESTIONS_DB.get(key, [])
    suggestion_list: List[SuggestionItem] = []

    # Personalize dplQueryParams with user's brand_code
    for s in base_list:
        item = s.model_copy(deep=True)
        item.dplQueryParams["brand_code"] = brand_code
        suggestion_list.append(item)

    loc = SuggestionLocationDetails(
        city="",
        countyCode="",
        countyName="",
        displayName=resolved_zip or "",
        distance="20",
        fipsStCd="",
        locationType="ZIP_CODE",
        stateCode=resolved_state or "",
        stateName="",
        zipCode=resolved_zip or "",
    )

    return FindCareSuggestionsResponse(
        primarySearchIntent=intent, suggestionList=suggestion_list, locationDetails=loc
    )


@app.post(
    "/get_medical_information",
    response_model=MedicalInformationResponse,
    tags=["Medical Info"],
)
def get_medical_information(
    query: str = Query(..., description='e.g., "high blood pressure", "diabetes"'),
    payload: GetMemberClaimsRequest = Body(
        ..., description="User context; memberId optional, location optional"
    ),
    page_index: int = Query(0, ge=0, description="Zero-based page index"),
    size: int = Query(5, ge=1, description="Page size (default 5)"),
):
    """
    Returns paginated medical articles for the given query (e.g., "high blood pressure", "diabetes", "knee surgery").
    """
    _ = payload  # accepted for API consistency; not required for medical info lookup
    norm_q = query.strip().lower()

    # 1) Collect results from seed KB (exact and fuzzy)
    items: list[MedicalArticle] = []
    # exact
    if norm_q in MEDICAL_KB:
        items.extend(MEDICAL_KB[norm_q])
    else:
        # fuzzy: include any topic where query matches or is contained in the KB key
        for k, v in MEDICAL_KB.items():
            if norm_q in k or k in norm_q:
                items.extend(v)

    # 2) If no seeded items, synthesize 6 generic articles (so pagination still works)
    if not items:
        base_url = "https://example.health/search"

        def _ct(en_us: str, en_ca: str, es_us: str) -> ConsumerText:
            return ConsumerText(
                consumer={"en-us": en_us, "en-ca": en_ca, "es-us": es_us}
            )

        title_q = query.strip().title() or "Medical Topic"
        synth: list[MedicalArticle] = []
        synth.append(
            MedicalArticle(
                id="gen-001",
                url=f"{base_url}?q={norm_q}&a=overview",
                title=_ct(
                    f"{title_q}: Overview",
                    f"{title_q}: Overview",
                    f"{title_q}: Descripción general",
                ),
                abstract=_ct(
                    f"An overview of {title_q}.",
                    f"An overview of {title_q}.",
                    f"Descripción general de {title_q}.",
                ),
            )
        )
        synth.append(
            MedicalArticle(
                id="gen-002",
                url=f"{base_url}?q={norm_q}&a=symptoms",
                title=_ct(
                    f"{title_q}: Symptoms",
                    f"{title_q}: Symptoms",
                    f"{title_q}: Síntomas",
                ),
                abstract=_ct(
                    f"Common and uncommon symptoms of {title_q}.",
                    f"Common and uncommon symptoms of {title_q}.",
                    f"Síntomas comunes e inusuales de {title_q}.",
                ),
            )
        )
        synth.append(
            MedicalArticle(
                id="gen-003",
                url=f"{base_url}?q={norm_q}&a=causes",
                title=_ct(
                    f"Causes of {title_q}",
                    f"Causes of {title_q}",
                    f"Causas de {title_q}",
                ),
                abstract=_ct(
                    f"Genetic, lifestyle, and other factors.",
                    f"Genetic, lifestyle, and other factors.",
                    f"Factores genéticos, de estilo de vida y otros.",
                ),
            )
        )
        synth.append(
            MedicalArticle(
                id="gen-004",
                url=f"{base_url}?q={norm_q}&a=diagnosis",
                title=_ct(
                    f"Diagnosing {title_q}",
                    f"Diagnosing {title_q}",
                    f"Diagnóstico de {title_q}",
                ),
                abstract=_ct(
                    f"How clinicians assess and confirm {title_q}.",
                    f"How clinicians assess and confirm {title_q}.",
                    f"CÓmo se evalúa y confirma {title_q}.",
                ),
            )
        )
        synth.append(
            MedicalArticle(
                id="gen-005",
                url=f"{base_url}?q={norm_q}&a=treatment",
                title=_ct(
                    f"Treatments for {title_q}",
                    f"Treatments for {title_q}",
                    f"Tratamientos para {title_q}",
                ),
                abstract=_ct(
                    f"Medications, procedures, and lifestyle changes.",
                    f"Medications, procedures, and lifestyle changes.",
                    f"Medicamentos, procedimientos y cambios de estilo de vida.",
                ),
            )
        )
        synth.append(
            MedicalArticle(
                id="gen-006",
                url=f"{base_url}?q={norm_q}&a=self-care",
                title=_ct(
                    f"Self-care Tips: {title_q}",
                    f"Self-care Tips: {title_q}",
                    f"Consejos de autocuidado: {title_q}",
                ),
                abstract=_ct(
                    f"Everyday steps to manage {title_q}.",
                    f"Everyday steps to manage {title_q}.",
                    f"Pasos diarios para manejar {title_q}.",
                ),
            )
        )
        items = synth

    # 3) Pagination
    total = len(items)
    start = page_index * size
    end = start + size
    page_items = items[start:end]

    # 4) Status
    status = (
        "OK" if page_items else ("NO_RESULTS" if total == 0 else "PAGE_OUT_OF_RANGE")
    )

    return MedicalInformationResponse(status=status, items=page_items)


@app.post("/get_claim_eob_pdf", response_model=EobPdfResponse, tags=["Claims"])
def get_claim_eob_pdf(
    clm_uid: str = Query(..., description="Claim UID (clmUid)"),
    payload: GetMemberClaimsRequest = Body(...),
):
    """Get EOB (explanation of benefits) detailed information for a specific claim."""
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Validate claim ownership
    claim = next((c for c in CLAIMS_DB if c.identifiers.uniqueId == clm_uid), None)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if payload.memberId not in (
        claim.parties.subject.identity.primaryId,
        claim.parties.subject.identity.secondaryId,
    ):
        raise HTTPException(status_code=403, detail="Claim does not belong to member")

    # Get EOBs from details DB
    details = CLAIM_DETAILS_DB.get(clm_uid, {})
    eobs = details.get("eobs") or []
    items = []
    for e in eobs:
        url = f"https://example.health/eob/{e.identifiers.uniqueId}.pdf"
        items.append(
            EobPdfItem(
                documentId=e.identifiers.uniqueId,
                documentUrl=url,
                contentType="application/pdf",
                fileSize=224_000,
            )
        )

    return EobPdfResponse(identifiers={"uniqueId": clm_uid}, explanations=items)


@app.post("/get_member_billing", response_model=BillingResponse, tags=["Billing"])
def get_member_billing(
    payload: GetMemberClaimsRequest = Body(...),
    page_index: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=100),
):
    """
    Get Billing information for a specific member.
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Claims owned by member (supports mbrUid or hcId)
    owned = [
        c
        for c in CLAIMS_DB
        if payload.memberId
        in (
            c.parties.subject.identity.primaryId,
            c.parties.subject.identity.secondaryId,
        )
    ]

    items: List[BillingItem] = []
    total_due = 0.0
    for c in owned:
        led = BILLING_LEDGER.get(c.identifiers.uniqueId)
        if not led:
            continue
        dueAmt = float(led.get("dueAmt", "0.00"))
        if led["status"] in ("DUE", "PARTIAL", "IN_COLLECTIONS") and dueAmt > 0:
            total_due += dueAmt
        items.append(
            BillingItem(
                identifiers={
                    "uniqueId": c.identifiers.uniqueId,
                    "displayId": c.identifiers.displayId,
                },
                amountDue=f"{dueAmt:.2f}",
                dueDate=led.get("dueDt"),
                paymentStatus=led["status"],
                onlinePaymentEnabled=c.flags.paymentEnabled,
            )
        )

    start = page_index * size
    end = start + size
    page_items = items[start:end]

    return BillingResponse(
        items=page_items,
        totals={
            "dueCount": str(
                sum(
                    1
                    for i in items
                    if i.paymentStatus != "PAID" and float(i.amountDue) > 0
                )
            ),
            "totalDueAmt": f"{total_due:.2f}",
        },
    )


@app.post(
    "/create_payment_intent",
    response_model=CreatePaymentIntentResponse,
    tags=["Billing"],
)
def create_payment_intent(
    amount: str = Query(..., description="Amount in USD, e.g., 60.00"),
    clm_uid: Optional[str] = Query(
        None, description="Optional claim UID to link payment"
    ),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Create a payment intent. Optionally connect to a specific claim.
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")
    # Optional ownership validation if clm_uid supplied
    if clm_uid:
        claim = next((c for c in CLAIMS_DB if c.identifiers.uniqueId == clm_uid), None)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        if payload.memberId not in (
            claim.parties.subject.identity.primaryId,
            claim.parties.subject.identity.secondaryId,
        ):
            raise HTTPException(
                status_code=403, detail="Claim does not belong to member"
            )

    pid = f"pi_{uuid4().hex[:24]}"
    client_secret = f"{pid}_secret_{uuid4().hex[:12]}"
    PAYMENT_INTENTS[pid] = {
        "status": "REQUIRES_CONFIRMATION",
        "memberId": payload.memberId,
        "clmUid": clm_uid or "",
        "amount": amount,
        "currency": "USD",
    }
    return CreatePaymentIntentResponse(
        transactionId=pid,
        state="REQUIRES_CONFIRMATION",
        authToken=client_secret,
        totalAmount=amount,
        currencyCode="USD",
        linkedClaim=clm_uid,
    )


@app.post(
    "/confirm_payment_intent",
    response_model=ConfirmPaymentIntentResponse,
    tags=["Billing"],
)
def confirm_payment_intent(
    payment_intent_id: str = Query(...),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Confirm an existing payment intent.
    """
    intent = PAYMENT_INTENTS.get(payment_intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="payment_intent not found")

    # Validate member matches creator
    if payload.memberId != intent["memberId"]:
        raise HTTPException(
            status_code=403, detail="payment_intent not owned by member"
        )

    # Mark succeeded
    intent["status"] = "SUCCEEDED"
    clm_uid = intent.get("clmUid") or None
    amount = intent.get("amount", "0.00")

    # If linked to a claim, mark ledger as PAID when amount covers due
    if clm_uid and clm_uid in BILLING_LEDGER:
        BILLING_LEDGER[clm_uid]["status"] = "PAID"
        BILLING_LEDGER[clm_uid]["dueAmt"] = "0.00"

    receipt_url = f"https://example.health/payments/{payment_intent_id}/receipt"

    return ConfirmPaymentIntentResponse(
        transactionId=payment_intent_id,
        state="SUCCEEDED",
        receiptUrl=receipt_url,
        totalAmount=amount,
        currencyCode="USD",
        linkedClaim=clm_uid,
    )


@app.post(
    "/get_benefit_accumulators",
    response_model=BenefitAccumulatorsResponse,
    tags=["Coverage"],
)
def get_benefit_accumulators(
    coverage_key: str = Query(...),
    payload: GetMemberClaimsRequest = Body(...),
):
    """
    Get benefit accumulators (deductibles, out of pocket, in and out of network) for a specific coverage key.
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Validate coverage belongs to member
    owner_mbr = COVERAGE_KEY_INDEX.get(coverage_key)
    if not owner_mbr:
        raise HTTPException(status_code=404, detail="coverage_key not found")
    # Accept if member is owner or same subscriber hcId
    if payload.memberId != owner_mbr:
        owner_elig = ELIGIBILITY_DB.get(owner_mbr)
        if not owner_elig:
            raise HTTPException(
                status_code=403, detail="coverage ownership could not be verified"
            )
        hcids = {e.identifiers.accountId for e in owner_elig.eligibility}
        if payload.memberId not in hcids and payload.memberId != owner_mbr:
            raise HTTPException(
                status_code=403, detail="coverage_key does not belong to member"
            )

    acc = ACCUMULATORS_DB.get(coverage_key)
    if not acc:
        raise HTTPException(status_code=404, detail="No accumulators for coverage_key")

    # Derive year from coverage
    elig = ELIGIBILITY_DB.get(owner_mbr)
    year = ""
    if elig and elig.eligibility:
        for e in elig.eligibility:
            for c in e.periods:
                if c.periodKey == coverage_key:
                    year = c.dates.start[:4]
                    break

    return BenefitAccumulatorsResponse(
        planYear=year or "2025", periodId=coverage_key, tracking=acc
    )


@app.post("/get_member_profile", response_model=MemberProfileResponse, tags=["Member"])
def get_member_profile(
    payload: GetMemberClaimsRequest = Body(...),
    active_only: bool = Query(
        True, description="Return only the active coverage household"
    ),
    pcp_provider_id: Optional[str] = Query("PRV-0106"),
):
    """
    Get member profile details and preferences.
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Find elig by memberId (can be mbrUid or hcId)
    elig = ELIGIBILITY_DB.get(payload.memberId)
    if payload.memberId == "121231235" or payload.memberId == "121231236":
        elig = ELIGIBILITY_DB.get("121231234")
    if not elig:
        # try to find by mbrUid -> lookup hcId stored key
        raise HTTPException(status_code=404, detail="Eligibility not found")

    # Build household from coverage.members
    household: List[MemberProfile] = []
    for e in elig.eligibility:
        for cov in e.periods:
            if active_only and (cov.status.identifier != "A"):
                continue
            for m in cov.enrollees:
                household.append(
                    MemberProfile(
                        identity={
                            "primaryId": m.personId,
                            "secondaryId": m.primaryAccountId,
                        },
                        identifiers={"accountId": m.primaryAccountId},
                        givenName=m.name.given,
                        familyName=m.name.family,
                        birthDate=m.birthDate,
                        relationship={
                            "identifier": m.relationship.identifier,
                            "label": m.relationship.label,
                            "details": m.relationship.details,
                        },
                    )
                )

    # Choose primary 'member' as the requester if present; else first in household
    primary = next(
        (
            h
            for h in household
            if h.identity["primaryId"] == payload.memberId
            or h.identifiers["accountId"] == payload.memberId
        ),
        None,
    ) or (household[0] if household else None)
    if not primary:
        raise HTTPException(status_code=404, detail="Member profile not found")
    # Preferences by primaryId
    prefs = MEMBER_PREFERENCES.get(primary.identity["primaryId"]) or MemberPreferences(
        language="en-us", emailOptIn=False, smsOptIn=False, accessibility=None
    )
    return MemberProfileResponse(
        member=primary,
        # household=household,
        preferences=prefs,
        pcpProviderId=pcp_provider_id,
    )


# ===== Plans Catalog Endpoints =====
# NOTE: /plans/compare MUST be declared before /plans/{plan_id} so FastAPI
# does not treat the literal "compare" as a plan_id path parameter.


@app.get("/plans", response_model=PlansListResponse, tags=["Plans"])
def list_plans(
    plan_type: Optional[str] = Query(
        None, description="Filter by plan type: PPO, HMO, EPO, HDHP, POS"
    ),
    market_segment: Optional[str] = Query(
        None, description="Filter by market segment: Individual, Group"
    ),
    hsa_eligible: Optional[bool] = Query(
        None, description="Filter to HSA-eligible plans only"
    ),
    max_premium: Optional[float] = Query(
        None, description="Max individual monthly premium in dollars (e.g. 400)"
    ),
):
    """List all available Oak health insurance plans. Supports filtering by plan type, HSA eligibility, and premium ceiling."""
    results = list(PLAN_CATALOG.values())

    if plan_type:
        results = [p for p in results if p.planType.upper() == plan_type.upper()]
    if market_segment:
        results = [
            p for p in results if p.marketSegment.lower() == market_segment.lower()
        ]
    if hsa_eligible is not None:
        results = [p for p in results if p.features.hsaEligible == hsa_eligible]
    if max_premium is not None:

        def _parse_premium(s: str) -> float:
            try:
                return float(s.replace("$", "").replace(",", ""))
            except Exception:
                return float("inf")

        results = [
            p
            for p in results
            if _parse_premium(p.estimatedMonthlyPremium.individual) <= max_premium
        ]

    # Return as PlanSummary (drop detail-only fields via model_dump slicing)
    summaries = [PlanSummary(**p.model_dump()) for p in results]
    return PlansListResponse(plans=summaries, totalCount=len(summaries))


@app.get("/plans/compare", response_model=PlanCompareResponse, tags=["Plans"])
def compare_plans(
    ids: str = Query(
        ...,
        description="Comma-separated plan IDs to compare, e.g. OAK-PPO-PREMIER-2025,OAK-HDHP-2025",
    ),
):
    """Compare 2–4 plans side by side. Pass comma-separated plan IDs via the ids parameter."""
    plan_ids = [i.strip() for i in ids.split(",") if i.strip()]
    if len(plan_ids) < 2:
        raise HTTPException(
            status_code=400, detail="At least 2 plan IDs are required for comparison"
        )
    if len(plan_ids) > 4:
        raise HTTPException(
            status_code=400, detail="At most 4 plans can be compared at once"
        )

    plans: List[PlanDetail] = []
    missing = []
    for pid in plan_ids:
        plan = PLAN_CATALOG.get(pid)
        if not plan:
            missing.append(pid)
        else:
            plans.append(plan)

    if missing:
        raise HTTPException(
            status_code=404, detail=f"Plan(s) not found: {', '.join(missing)}"
        )

    return PlanCompareResponse(
        plans=plans,
        comparisonDimensions=[
            "estimatedMonthlyPremium.individual",
            "estimatedMonthlyPremium.family",
            "deductibleType",
            "innCoverage.individualDeductible",
            "innCoverage.familyDeductible",
            "innCoverage.individualOopMax",
            "innCoverage.familyOopMax",
            "innCoverage.primaryCareCopay",
            "innCoverage.specialistCopay",
            "innCoverage.erCopay",
            "innCoverage.imaging",
            "drugCoverage.tier1Generic",
            "drugCoverage.tier4Specialty",
            "features.outOfNetworkCoverage",
            "features.referralRequired",
            "features.hsaEligible",
            "specialBenefits.telehealthCopay",
            "specialBenefits.pediatricDental",
        ],
    )


@app.get("/plans/{plan_id}", response_model=PlanDetailResponse, tags=["Plans"])
def get_plan(plan_id: str):
    """Get full cost-sharing details, drug tiers, and network info for a single plan."""
    plan = PLAN_CATALOG.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
    return PlanDetailResponse(plan=plan)


@app.post("/set_member_preferences", response_model=MemberPreferences, tags=["Member"])
def set_member_preferences(
    payload: GetMemberClaimsRequest = Body(...),
    language: Optional[str] = Query(None, description="e.g., en-us"),
    emailOptIn: Optional[bool] = Query(None),
    smsOptIn: Optional[bool] = Query(None),
    # accessibility: Optional[str] = Query(None),
):
    """
    Set member preferences (language, emails, SMS, accessibility).
    """
    if not payload.memberId:
        raise HTTPException(status_code=400, detail="memberId is required")

    # Resolve to an mbrUid (if payload.memberId is hcId, find subscriber/member entry)
    mbr_uid = payload.memberId
    if mbr_uid not in MEMBER_PREFERENCES:
        # try to find a matching member in eligibility to map hcId->mbrUid
        elig = ELIGIBILITY_DB.get(payload.memberId)
        if elig and elig.eligibility:
            # choose subscriber when available
            subs = [
                m
                for e in elig.eligibility
                for c in e.periods
                for m in c.enrollees
                if m.relationship.identifier == "SUBSCR"
            ]
            if subs:
                mbr_uid = subs[0].personId

    current = MEMBER_PREFERENCES.get(mbr_uid) or MemberPreferences(
        language="en-us", emailOptIn=False, smsOptIn=False, accessibility=None
    )
    updated = MemberPreferences(
        language=language if language is not None else current.language,
        emailOptIn=emailOptIn if emailOptIn is not None else current.emailOptIn,
        smsOptIn=smsOptIn if smsOptIn is not None else current.smsOptIn,
        accessibility=current.accessibility,
    )
    MEMBER_PREFERENCES[mbr_uid] = updated
    return updated


def main():
    import uvicorn

    uvicorn.run("oak_health.main:app", host="0.0.0.0", port=8090)


if __name__ == "__main__":
    main()

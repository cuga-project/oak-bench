from typing import List, Dict, Tuple, Optional
from oak_health.models import (
    # Core shared models (transformed)
    MetadataTriple,
    PersonRecord,
    PersonIdentity,
    FinancialBreakdown,
    ServiceEntity,
    CostAllocation,
    CostSharing,
    PaymentSummary,
    PlanBenefits,
    # Claims models (transformed)
    ServiceRecord,
    ServiceLineItem,
    ExplanationRecord,
    MedicalCode,
    DiagnosisSet,
    RecordIdentifiers,
    RecordFlags,
    RecordClassification,
    ServiceTimeline,
    ServiceParties,
    LineItemPeriod,
    LineItemFinancials,
    ExplanationIdentifiers,
    PaymentDetails,
    # Coverage/Plan models (transformed)
    CoveragePeriodResponse,
    ContractRecord,
    EnrollmentPeriod,
    EnrolledPerson,
    ProductType,
    Vendor,
    ContractIdentifiers,
    GroupInfo,
    PeriodDates,
    PeriodFeatures,
    PersonName,
    EnrollmentDates,
    RelationshipCd,
    GenderCd,
    PlanInformationResponse,
    BenefitPeriod,
    ValueBasedProviderInfo,
    NetworkPlan,
    CostShareEntry,
    BenefitItem,
    # Search benefits models (transformed)
    BenefitsSearchResponse,
    CoverageInquiryResult,
    ProductCategory,
    CategoryEntry,
    ServiceEntry,
    CoverageSpecification,
    CoverageScenario,
    POS,
    NetworkCostStructure,
    CostComponent,
    RelatedProcedure,
    InquiryContext,
    # Detail models
    DetailCostComponent,
    DetailNetworkCostStructure,
    DetailPOS,
    DetailCoverageScenario,
    ServiceBenefitDetail,
    ServiceDetailsGroup,
    ServiceCategoryDetails,
    PlanLevelBenefitsGroup,
    PlanLevelEntry,
    BenefitDetailsResult,
    BenefitsDetailsResponse,
    # Find care specialty (transformed)
    CareProviderProfile,
    LocationDetails,
    AddressComponents,
    ContactInfo,
    GeoCoordinates,
    ProviderTaxonomy,
    NetworkParticipation,
    ExpertiseProfile,
    FindCareSpecialtyResponse,
    # Suggestions (transformed)
    FindCareSuggestionsResponse,
    SuggestionItem,
    SuggestionCriteria,
    SuggestionLocationDetails,
    ProviderTaxonomy,
    # Medical info
    MedicalInformationResponse,
    MedicalArticle,
    ConsumerText,
    # additional
    EobPdfItem,
    EobPdfResponse,
    BillingItem,
    BillingResponse,
    CreatePaymentIntentResponse,
    ConfirmPaymentIntentResponse,
    AccumulatorEntry,
    BenefitAccumulatorsResponse,
    MemberPreferences,
    MemberProfileResponse,
    MemberProfile,
    # Plans catalog
    PlanPremium,
    PlanNetworkInfo,
    PlanFeatures,
    CostStructure,
    DrugTiers,
    SpecialBenefits,
    PlanSummary,
    PlanDetail,
    PlansListResponse,
    PlanDetailResponse,
    PlanCompareResponse,
)

# =====================================================
# Shared codebooks and helper builders
# =====================================================

CLM_SOURCE_WGS20 = MetadataTriple(identifier="808", label="WGS20", details="WGS20")
CLM_CLASS_MEDICAL = MetadataTriple(
    identifier="M", label="Medical Claim", details="Medical Claim"
)
CLM_TYPE_PROF = MetadataTriple(
    identifier="PR", label="Professional", details="Professional Claim"
)

STATUS_CODEBOOK = {
    "APRVD": MetadataTriple(
        identifier="APRVD",
        label="Approved",
        details="What does an approved claim mean? We finished reviewing this claim and approved the claim under your plan.",
    ),
    "DND": MetadataTriple(
        identifier="DND",
        label="Denied",
        details="Why was this claim denied? Common reasons are that we received the same claim twice, or the service performed is not covered under your plan.",
    ),
    "PEND": MetadataTriple(
        identifier="PEND",
        label="Pending",
        details="This claim is in review. We’ll update once processing is complete.",
    ),
    "PROC": MetadataTriple(
        identifier="PROC",
        label="Processing",
        details="We are currently processing this claim.",
    ),
}


def amt(
    allowed="10.00",
    coins="0.00",
    copay="0.00",
    ded="0.00",
    mbr="0.00",
    prov="0.00",
    notcov="0.00",
    save="0.00",
    disc="0.00",
    paid="0.00",
    total="10.00",
    gross="0.00",
    charge=None,
) -> FinancialBreakdown:
    return FinancialBreakdown(
        allocation=CostAllocation(
            approved=allowed, patientShare=mbr, providerShare=prov, excluded=notcov
        ),
        sharing=CostSharing(coinsurance=coins, fixedFee=copay, deductible=ded),
        payment=PaymentSummary(
            disbursed=paid, billed=total, gross=gross, service=charge
        ),
        benefits=PlanBenefits(discount=disc, savings=save),
    )


def masked_providers() -> Tuple[ServiceEntity, ServiceEntity]:
    servicing = ServiceEntity(entityName="#%sensitive#%", taxIdentifier=None)
    billing = ServiceEntity(entityName="#%sensitive#%", taxIdentifier="#%sensitive#%")
    return servicing, billing


def patient_john() -> PersonRecord:
    return PersonRecord(
        identity=PersonIdentity(primaryId="121231234", secondaryId="868Y10397"),
        givenName="JOHN",
        familyName="DOE",
        birthDate="1970-02-13",
    )


def patient_alt() -> PersonRecord:
    return PersonRecord(
        identity=PersonIdentity(primaryId="882771300", secondaryId="441Z22001"),
        givenName="JANE",
        familyName="DOE",
        birthDate="1985-04-21",
    )


# =====================================================
# Claims seeding + details
# =====================================================


def build_claim(
    clmUid: str,
    clmId: str,
    clmRefId: str,
    status_code: str,
    start: str,
    end: str,
    recv: str,
    proc: str,
    patient: PersonRecord,
    amount: FinancialBreakdown,
    cdhp="N",
    enableBillPay="Y",
    sensitive="Y",
    capitated="N",
    network="Y",
) -> ServiceRecord:
    sp, bp = masked_providers()
    return ServiceRecord(
        identifiers=RecordIdentifiers(
            uniqueId=clmUid, displayId=clmId, referenceId=clmRefId
        ),
        flags=RecordFlags(
            accountType=(cdhp.upper() == "Y"),
            paymentEnabled=(enableBillPay.upper() == "Y"),
            confidential=(sensitive.upper() == "Y"),
            prepaidService=(capitated.upper() == "Y"),
            minorProtected=None,
        ),
        classification=RecordClassification(
            source=CLM_SOURCE_WGS20,
            category=CLM_CLASS_MEDICAL,
            type=CLM_TYPE_PROF,
            status=STATUS_CODEBOOK[status_code],
        ),
        timeline=ServiceTimeline(
            serviceStart=start, serviceEnd=end, received=recv, processed=proc
        ),
        parties=ServiceParties(subject=patient, servicingEntity=sp, billingEntity=bp),
        financial=amount,
        networkIdentifier=network,
        lineItems=None,
        explanations=None,
    )


def seed_claims() -> List[ServiceRecord]:
    claims: List[ServiceRecord] = []

    # Member 1 (JOHN)
    john = patient_john()
    claims.append(
        build_claim(
            clmUid="451F6F37F295390506B9CF9F6DFBC930",
            clmId="2025034AA1251",
            clmRefId="AB31155D94A4059C8793CE365B429168",
            status_code="APRVD",
            start="2025-02-02",
            end="2025-02-02",
            recv="2025-02-03",
            proc="2025-02-04",
            patient=john,
            amount=amt(allowed="10.00", paid="10.00", total="10.00", save="10.00"),
        )
    )
    claims.append(
        build_claim(
            clmUid="63FA69DB119C2E16E21B487BC411E1F2",
            clmId="2025034AA2251",
            clmRefId="4D845B9FCA7EA6FCEC36755C68342BC8",
            status_code="DND",
            start="2025-01-31",
            end="2025-01-31",
            recv="2025-02-03",
            proc="2025-02-04",
            patient=john,
            amount=amt(mbr="10.00", notcov="10.00", total="10.00", allowed="10.00"),
        )
    )
    claims.append(
        build_claim(
            clmUid="B1E7C2D8A9F048B7B2A9DCE431F0CD10",
            clmId="2025034AA3251",
            clmRefId="2A0A5B3F9F114F8F8A9D3B1E1AA22F77",
            status_code="PEND",
            start="2025-07-05",
            end="2025-07-05",
            recv="2025-07-06",
            proc="2025-07-06",
            patient=john,
            amount=amt(
                allowed="200.00",
                copay="20.00",
                total="220.00",
                paid="0.00",
                save="0.00",
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8D7A6B5A4899BC12EF3344CDA123",
            clmId="2025034AA4251",
            clmRefId="7E2F1B4C9DAE4B7E9A1C2D3F4B5C6D70",
            status_code="PROC",
            start="2025-01-20",
            end="2025-01-20",
            recv="2025-01-21",
            proc="2025-01-22",
            patient=john,
            amount=amt(
                allowed="75.00", paid="60.00", mbr="15.00", total="75.00", save="15.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8D7A6B5A489AAC12EF3344CDA1Aq",
            clmId="2025034AA5001",
            clmRefId="7E2F1B4C9DAE4B7E9A1C2D3F4B5C6D11",
            status_code="APRVD",
            start="2025-02-10",
            end="2025-02-10",
            recv="2025-02-11",
            proc="2025-02-12",
            patient=john,
            amount=amt(
                allowed="90.00", paid="72.00", mbr="18.00", total="90.00", save="18.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="7E2F1B4C9DAAAB7E9A1C2D3F4B5C6D70",
            clmId="2025034AA5002",
            clmRefId="7E2F1B4C9DAE4B7E9A1C2D3F4B5C6D777",
            status_code="DND",
            start="2025-02-12",
            end="2025-02-12",
            recv="2025-02-13",
            proc="2025-02-14",
            patient=john,
            amount=amt(
                allowed="150.00",
                notcov="150.00",
                mbr="150.00",
                total="150.00",
                paid="0.00",
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="7E2F1AQQ9DAE4B7E9A1C2D3F4B5C6D70",
            clmId="2025034AA5003",
            clmRefId="7E2F1B4C9DAE4B7E9A1C2D3F4B5CAWT65",
            status_code="PROC",
            start="2025-02-15",
            end="2025-02-15",
            recv="2025-02-16",
            proc="2025-02-17",
            patient=john,
            amount=amt(
                allowed="65.00", paid="50.00", mbr="15.00", total="65.00", save="15.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="7E2F1B4C9DAE4B7E9A1C2D3F4B5C2687",
            clmId="2025034AA5004",
            clmRefId="7E2F1B4C9DAE4B7E9A1C2D3F12311A",
            status_code="PEND",
            start="2025-02-20",
            end="2025-02-20",
            recv="2025-02-21",
            proc="2025-02-21",
            patient=john,
            amount=amt(
                allowed="210.00",
                copay="25.00",
                mbr="25.00",
                total="235.00",
                paid="0.00",
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="7E2F1B4C9DAE4B7E9A1NNT1F4B5C6D70",
            clmId="2025034AA5005",
            clmRefId="7E2F1B4C9DA22B7E9A1C2D3F4B5C6D22",
            status_code="APRVD",
            start="2025-02-25",
            end="2025-02-25",
            recv="2025-02-26",
            proc="2025-02-27",
            patient=john,
            amount=amt(
                allowed="40.00", paid="40.00", mbr="0.00", total="40.00", save="10.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8Q1A6B28411BA3A2333AQW1DA213",
            clmId="2025034AA5006",
            clmRefId="REF9C0C8Q1A6B28411BA3A2333AQW1DA213",
            status_code="APRVD",
            start="2025-03-01",
            end="2025-03-01",
            recv="2025-03-02",
            proc="2025-03-03",
            patient=john,
            amount=amt(
                allowed="120.00",
                paid="96.00",
                mbr="24.00",
                total="120.00",
                save="30.00",
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8D7A6B5A4899BC12EF3344CDA456",
            clmId="2025034AA5007",
            clmRefId="REF9C0C8D7A6B5A4899BC12EF3344CDA456",
            status_code="DND",
            start="2025-03-05",
            end="2025-03-05",
            recv="2025-03-06",
            proc="2025-03-07",
            patient=john,
            amount=amt(
                allowed="80.00", notcov="80.00", mbr="80.00", total="80.00", paid="0.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8Q1A6B28A2ABA3A2333AQW1DA888",
            clmId="2025034AA5008",
            clmRefId="REF9C0C8Q1A6B28A2ABA3A2333AQW1DA888",
            status_code="PROC",
            start="2025-03-10",
            end="2025-03-10",
            recv="2025-03-11",
            proc="2025-03-12",
            patient=john,
            amount=amt(
                allowed="55.00", paid="44.00", mbr="11.00", total="55.00", save="11.00"
            ),
        )
    )
    # Dependent patients for claims context (share subscriber's hcId)
    sara_patient = PersonRecord(
        identity=PersonIdentity(
            primaryId="121231235", secondaryId=john.identity.secondaryId
        ),
        givenName="SARA",
        familyName="DOE",
        birthDate="2008-06-10",
    )
    tom_patient = PersonRecord(
        identity=PersonIdentity(
            primaryId="121231236", secondaryId=john.identity.secondaryId
        ),
        givenName="TOM",
        familyName="DOE",
        birthDate="2012-09-15",
    )

    # Claims for SARA (approved & denied)
    claims.append(
        build_claim(
            clmUid="9CUY8Q1A6B28A2ABA3KI333AQW1DA557",
            clmId="2025034CHILD01",
            clmRefId="REF9CUY8Q1A6B28A2ABA3KI333AQW1DA557",
            status_code="APRVD",
            start="2025-02-08",
            end="2025-02-08",
            recv="2025-02-09",
            proc="2025-02-10",
            patient=sara_patient,
            amount=amt(
                allowed="85.00", paid="85.00", mbr="0.00", total="85.00", save="20.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8D7A6B5A499BA3A4F33AQW1DA211",
            clmId="2025034CHILD02",
            clmRefId="REF9C0C8D7A6B5A499BA3A4F33AQW1DA211",
            status_code="PEND",
            start="2025-03-02",
            end="2025-03-02",
            recv="2025-03-03",
            proc="2025-03-04",
            patient=sara_patient,
            amount=amt(
                allowed="60.00", notcov="60.00", mbr="60.00", total="60.00", paid="0.00"
            ),
        )
    )

    # Claims for TOM (approved & denied)
    claims.append(
        build_claim(
            clmUid="9C0C8D7A6B5A4899BA3A4F3344CDA451",
            clmId="2025034CHILD03",
            clmRefId="REF9C0C8D7A6B5A4899BA3A4F3344CDA451",
            status_code="APRVD",
            start="2025-02-18",
            end="2025-02-18",
            recv="2025-02-19",
            proc="2025-02-20",
            patient=tom_patient,
            amount=amt(
                allowed="70.00", paid="56.00", mbr="14.00", total="70.00", save="14.00"
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="9C0C8Q1A6B28499BA3A2333AQW1DAADE",
            clmId="2025034CHILD04",
            clmRefId="REF9C0C8Q1A6B28499BA3A2333AQW1DAADE",
            status_code="DND",
            start="2025-03-06",
            end="2025-03-06",
            recv="2025-03-07",
            proc="2025-03-08",
            patient=tom_patient,
            amount=amt(
                allowed="95.00", notcov="95.00", mbr="95.00", total="95.00", paid="0.00"
            ),
        )
    )

    # Member 2 (JANE)
    jane = patient_alt()
    claims.append(
        build_claim(
            clmUid="A1111111111111111111111111111111",
            clmId="2025034BB1251",
            clmRefId="B2222222222222222222222222222222",
            status_code="APRVD",
            start="2025-01-15",
            end="2025-01-15",
            recv="2025-01-16",
            proc="2025-01-18",
            patient=jane,
            amount=amt(
                allowed="320.00",
                paid="280.00",
                mbr="40.00",
                total="320.00",
                save="40.00",
            ),
        )
    )
    claims.append(
        build_claim(
            clmUid="C3333333333333333333333333333333",
            clmId="2025034BB2251",
            clmRefId="D4444444444444444444444444444444",
            status_code="DND",
            start="2025-02-10",
            end="2025-02-10",
            recv="2025-02-11",
            proc="2025-02-12",
            patient=jane,
            amount=amt(allowed="50.00", notcov="50.00", total="50.00", paid="0.00"),
        )
    )
    return claims


def _line(
    start: str,
    end: str,
    proc_code: str,
    dx_codes: List[str],
    allowed: str,
    deductible: str,
    coins: str,
    copay: str,
    mbr: str,
    notcov: str,
    save: str,
    disc: str,
    charge: str,
    paid: str,
) -> ServiceLineItem:
    return ServiceLineItem(
        period=LineItemPeriod(start=start, end=end),
        financials=LineItemFinancials(
            approved=allowed,
            deductible=deductible,
            coinsurance=coins,
            fixedFee=copay,
            patientOwes=mbr,
            notCovered=notcov,
            planSavings=save,
            planDiscount=disc,
            charged=charge,
            paid=paid,
        ),
        procedure=MedicalCode(code=proc_code),
        diagnosisSets=[DiagnosisSet(codes=[MedicalCode(code=c) for c in dx_codes])],
    )


def _eob(
    eobUid: str,
    sorCd: str,
    mbrid: str,
    eobDt: str,
    seq: str,
    checkNbr: str,
    checkDt: str,
    clmId: str,
    start: str,
    end: str,
    procDt: str,
    subscriberNm: str,
    patientNm: str,
    legacyId: str = "",
    uwState: str = "",
) -> ExplanationRecord:
    return ExplanationRecord(
        identifiers=ExplanationIdentifiers(
            uniqueId=eobUid,
            sourceSystem=sorCd,
            memberId=mbrid,
            sequenceNumber=seq,
            legacyReference=legacyId or None,
        ),
        date=eobDt,
        payment=PaymentDetails(checkNumber=checkNbr or None, checkDate=checkDt or None),
        relatedRecordId=clmId,
        serviceStart=start,
        serviceEnd=end,
        processedDate=procDt,
        subscriberName=subscriberNm,
        patientName=patientNm,
        jurisdiction=uwState or None,
    )


def build_claim_details_index(
    claims: List[ServiceRecord],
) -> Dict[str, Dict[str, List]]:
    by_uid: Dict[str, Dict[str, List]] = {}

    def fullname(p: PersonRecord) -> str:
        return f"{p.givenName} {p.familyName}".strip()

    for c in claims:
        lines: List[ServiceLineItem] = [
            _line(
                start=c.timeline.serviceStart,
                end=c.timeline.serviceEnd,
                proc_code="99213",
                dx_codes=["Z00.00"],
                allowed=c.financial.allocation.approved or "0.00",
                deductible=c.financial.sharing.deductible or "0.00",
                coins=c.financial.sharing.coinsurance or "0.00",
                copay=c.financial.sharing.fixedFee or "0.00",
                mbr=c.financial.allocation.patientShare or "0.00",
                notcov=c.financial.allocation.excluded or "0.00",
                save=c.financial.benefits.savings or "0.00",
                disc=c.financial.benefits.discount or "0.00",
                charge=c.financial.payment.billed
                or c.financial.payment.service
                or "0.00",
                paid=c.financial.payment.disbursed or "0.00",
            )
        ]
        eobs: List[ExplanationRecord] = []

        if c.classification.status.identifier in ("APRVD", "PROC"):
            eobs.append(
                _eob(
                    eobUid=f"EOB-{c.identifiers.uniqueId[:8]}",
                    sorCd="EOBSYS",
                    mbrid=c.parties.subject.identity.primaryId,
                    eobDt=c.timeline.processed,
                    seq="1",
                    checkNbr="100200300"
                    if c.financial.payment.disbursed
                    and float(c.financial.payment.disbursed) > 0
                    else "",
                    checkDt=c.timeline.processed
                    if c.financial.payment.disbursed
                    and float(c.financial.payment.disbursed) > 0
                    else "",
                    clmId=c.identifiers.displayId,
                    start=c.timeline.serviceStart,
                    end=c.timeline.serviceEnd,
                    procDt=c.timeline.processed,
                    subscriberNm=fullname(c.parties.subject),
                    patientNm=fullname(c.parties.subject),
                    legacyId=f"LEG-{c.identifiers.displayId[-4:]}",
                    uwState="NY",
                )
            )

        # Specialize lines per seeded claims to align with summary amounts
        if c.identifiers.uniqueId == "451F6F37F295390506B9CF9F6DFBC930":
            lines = [
                _line(
                    c.timeline.serviceStart,
                    c.timeline.serviceEnd,
                    "99213",
                    ["Z00.00"],
                    "10.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "10.00",
                    "0.00",
                    "10.00",
                    "10.00",
                )
            ]
        if c.identifiers.uniqueId == "63FA69DB119C2E16E21B487BC411E1F2":
            lines = [
                _line(
                    c.timeline.serviceStart,
                    c.timeline.serviceEnd,
                    "97110",
                    ["M25.50"],
                    "10.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "10.00",
                    "10.00",
                    "0.00",
                    "0.00",
                    "10.00",
                    "0.00",
                )
            ]
        if c.identifiers.uniqueId == "B1E7C2D8A9F048B7B2A9DCE431F0CD10":
            lines = [
                _line(
                    c.timeline.serviceStart,
                    c.timeline.serviceEnd,
                    "93000",
                    ["R51"],
                    "200.00",
                    "0.00",
                    "0.00",
                    "20.00",
                    "20.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "220.00",
                    "0.00",
                )
            ]
        if c.identifiers.uniqueId == "9C0C8D7A6B5A4899BC12EF3344CDA123":
            lines = [
                _line(
                    c.timeline.serviceStart,
                    c.timeline.serviceEnd,
                    "80050",
                    ["J06.9"],
                    "75.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "15.00",
                    "0.00",
                    "15.00",
                    "0.00",
                    "75.00",
                    "60.00",
                )
            ]
        if c.identifiers.uniqueId == "A1111111111111111111111111111111":
            lines = [
                _line(
                    c.timeline.serviceStart,
                    c.timeline.serviceEnd,
                    "99214",
                    ["I10"],
                    "320.00",
                    "0.00",
                    "0.00",
                    "0.0",
                    "40.00",
                    "0.0",
                    "40.00",
                    "0.0",
                    "320.00",
                    "280.00",
                )
            ]
        if c.identifiers.uniqueId == "C3333333333333333333333333333333":
            lines = [
                _line(
                    c.timeline.serviceStart,
                    c.timeline.serviceEnd,
                    "97140",
                    ["M54.5"],
                    "50.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "50.00",
                    "50.00",
                    "0.00",
                    "0.00",
                    "50.00",
                    "0.00",
                )
            ]

        by_uid[c.identifiers.uniqueId] = {"serviceLines": lines, "eobs": eobs}

    return by_uid


# =====================================================
# Coverage & Plan seeding
# =====================================================


def _rel(code: str, name: str) -> RelationshipCd:
    return RelationshipCd(code=code, name=name, description=name)


def _gender(code: str, name: str) -> GenderCd:
    return GenderCd(code=code, name=name, description=name)


def seed_eligibility_and_plans():
    """
    Returns:
      ELIGIBILITY_DB: dict[str -> CoveragePeriodResponse] (keyed by mbrUid and hcId)
      COVERAGE_KEY_INDEX: dict[coverage_key -> owner_mbrUid]
      PLAN_INFO_DB: dict[(coverage_key, opted_plan_type) -> PlanInformationResponse]
      CONTRACT_UID_TO_CD: dict[contract_uid -> contractCd]
    """
    ELIGIBILITY_DB: Dict[str, CoveragePeriodResponse] = {}
    COVERAGE_KEY_INDEX: Dict[str, str] = {}
    PLAN_INFO_DB: Dict[tuple, PlanInformationResponse] = {}
    CONTRACT_UID_TO_CD: Dict[str, str] = {}

    # ----- John -----
    john = patient_john()
    john_cov_key_2025 = "1J1U-20250101-20251231-MED-57AMFC"
    john_cov_key_2024 = "1J1U-20240101-20241231-MED-OLDPPO"
    COVERAGE_KEY_INDEX[john_cov_key_2025] = john.identity.primaryId
    COVERAGE_KEY_INDEX[john_cov_key_2024] = john.identity.primaryId

    john_coverage_2025 = EnrollmentPeriod(
        periodKey=john_cov_key_2025,
        dates=PeriodDates(start="2025-01-01", end="2025-12-31"),
        features=PeriodFeatures(
            salaryBasedLimit=False,  # maxOOPSalaryInd="N"
            enhancedProgram=True,  # isCoupeHealth=True
            dependentEligible=True,  # minorAvailable=True
        ),
        enrollmentType=MetadataTriple(
            identifier="ENR", label="Enrolled", details="Enrolled"
        ),
        status=MetadataTriple(
            identifier="A", label="Active", details="Active Coverage"
        ),
        productTypes=[
            ProductType(
                coverageTypeCd=MetadataTriple(
                    identifier="MED", label="Medical", details="Medical Coverage"
                ),
                vendor=[Vendor(vendorNm="Acme Health")],
            )
        ],
        productName="Acme Standard PPO",
        systemReference="BEN-SYS-01",
        enrollees=[
            EnrolledPerson(
                personId=john.identity.primaryId,
                name=PersonName(
                    given=john.givenName, middle=None, family=john.familyName
                ),
                birthDate=john.birthDate,
                relationship=MetadataTriple(
                    identifier="SUBSCR", label="Subscriber", details="Subscriber"
                ),
                enrollment=EnrollmentDates(
                    effective="2025-01-01", termination="2025-12-31"
                ),
                status=MetadataTriple(identifier="A", label="Active", details="Active"),
                productTypes=[
                    MetadataTriple(identifier="MED", label="Medical", details="Medical")
                ],
                sequenceNumber="01",
                primaryAccountId=john.identity.secondaryId,
                gender=MetadataTriple(identifier="M", label="Male", details="Male"),
            ),
            EnrolledPerson(
                personId="121231235",
                name=PersonName(given="SARA", middle=None, family="DOE"),
                birthDate="2008-06-10",
                relationship=MetadataTriple(
                    identifier="CHILD", label="Child", details="Child"
                ),
                enrollment=EnrollmentDates(
                    effective="2025-01-01", termination="2025-12-31"
                ),
                status=MetadataTriple(identifier="A", label="Active", details="Active"),
                productTypes=[
                    MetadataTriple(identifier="MED", label="Medical", details="Medical")
                ],
                sequenceNumber="02",
                primaryAccountId=john.identity.secondaryId,
                gender=MetadataTriple(identifier="F", label="Female", details="Female"),
            ),
            EnrolledPerson(
                personId="121231236",
                name=PersonName(given="TOM", middle=None, family="DOE"),
                birthDate="2012-09-15",
                relationship=MetadataTriple(
                    identifier="CHILD", label="Child", details="Child"
                ),
                enrollment=EnrollmentDates(
                    effective="2025-01-01", termination="2025-12-31"
                ),
                status=MetadataTriple(identifier="A", label="Active", details="Active"),
                productTypes=[
                    MetadataTriple(identifier="MED", label="Medical", details="Medical")
                ],
                sequenceNumber="03",
                primaryAccountId=john.identity.secondaryId,
                gender=MetadataTriple(identifier="M", label="Male", details="Male"),
            ),
        ],
        benefitCycle="CY",
        arrangement=MetadataTriple(
            identifier="PPO", label="Preferred Provider Organization", details="PPO"
        ),
    )

    john_coverage_2024 = EnrollmentPeriod(
        periodKey=john_cov_key_2024,
        dates=PeriodDates(start="2024-01-01", end="2024-12-31"),
        features=PeriodFeatures(
            salaryBasedLimit=False, enhancedProgram=False, dependentEligible=True
        ),
        enrollmentType=MetadataTriple(
            identifier="ENR", label="Enrolled", details="Enrolled"
        ),
        status=MetadataTriple(
            identifier="I", label="Inactive", details="Inactive Coverage"
        ),
        productTypes=[
            ProductType(
                coverageTypeCd=MetadataTriple(
                    identifier="MED", label="Medical", details="Medical Coverage"
                ),
                vendor=[Vendor(vendorNm="Legacy Health")],
            )
        ],
        productName="Legacy PPO",
        systemReference="BEN-SYS-00",
        enrollees=[
            EnrolledPerson(
                personId=john.identity.primaryId,
                name=PersonName(
                    given=john.givenName, middle=None, family=john.familyName
                ),
                birthDate=john.birthDate,
                relationship=MetadataTriple(
                    identifier="SUBSCR", label="Subscriber", details="Subscriber"
                ),
                enrollment=EnrollmentDates(
                    effective="2024-01-01", termination="2024-12-31"
                ),
                status=MetadataTriple(
                    identifier="I", label="Inactive", details="Inactive"
                ),
                productTypes=[
                    MetadataTriple(identifier="MED", label="Medical", details="Medical")
                ],
                sequenceNumber="01",
                primaryAccountId=john.identity.secondaryId,
                gender=MetadataTriple(identifier="M", label="Male", details="Male"),
            ),
            EnrolledPerson(
                personId="121231233",
                name=PersonName(given="Jenny", middle=None, family=john.familyName),
                birthDate=john.birthDate,
                relationship=MetadataTriple(
                    identifier="SPOU", label="Spouse", details="Spouse"
                ),
                enrollment=EnrollmentDates(
                    effective="2024-01-01", termination="2024-12-31"
                ),
                status=MetadataTriple(
                    identifier="I", label="Inactive", details="Inactive"
                ),
                productTypes=[
                    MetadataTriple(identifier="MED", label="Medical", details="Medical")
                ],
                sequenceNumber="01",
                primaryAccountId=john.identity.secondaryId,
                gender=MetadataTriple(identifier="F", label="Female", details="Female"),
            ),
        ],
        benefitCycle="CY",
        arrangement=MetadataTriple(
            identifier="PPO", label="Preferred Provider Organization", details="PPO"
        ),
    )

    john_elig = ContractRecord(
        identifiers=ContractIdentifiers(
            accountId=john.identity.secondaryId,
            contractNumber="CNTR-1001",
            contractUniqueId="CONTRACT-UID-JOHN-1001",
        ),
        group=GroupInfo(groupId="GRP-ACME", groupName="Acme Corp"),
        effectiveDate="2024-01-01",
        status=MetadataTriple(
            identifier="A", label="Active", details="Active at contract level"
        ),
        brand=MetadataTriple(
            identifier="ACME", label="ACME HEALTH", details="ACME HEALTH"
        ),
        sourceSystem="ELIGSYS",
        periods=[john_coverage_2024, john_coverage_2025],
    )
    ELIGIBILITY_DB[john.identity.primaryId] = CoveragePeriodResponse(
        eligibility=[john_elig]
    )
    ELIGIBILITY_DB[john.identity.secondaryId] = ELIGIBILITY_DB[john.identity.primaryId]
    CONTRACT_UID_TO_CD["CONTRACT-UID-JOHN-1001"] = "1J1U"

    # ----- JANE -----
    jane = patient_alt()
    jane_cov_key_2025 = "9Z9X-20250101-20251231-MED-INDHMO"
    COVERAGE_KEY_INDEX[jane_cov_key_2025] = jane.identity.primaryId

    jane_coverage_2025 = EnrollmentPeriod(
        periodKey=jane_cov_key_2025,
        dates=PeriodDates(start="2025-01-01", end="2025-12-31"),
        features=PeriodFeatures(
            salaryBasedLimit=False, enhancedProgram=False, dependentEligible=False
        ),
        enrollmentType=MetadataTriple(
            identifier="ENR", label="Enrolled", details="Enrolled"
        ),
        status=MetadataTriple(
            identifier="A", label="Active", details="Active Coverage"
        ),
        productTypes=[
            ProductType(
                coverageTypeCd=MetadataTriple(
                    identifier="MED", label="Medical", details="Medical Coverage"
                ),
                vendor=[Vendor(vendorNm="Vista Health")],
            )
        ],
        productName="Vista HMO Bronze",
        systemReference="BEN-SYS-11",
        enrollees=[
            EnrolledPerson(
                personId=jane.identity.primaryId,
                name=PersonName(
                    given=jane.givenName, middle=None, family=jane.familyName
                ),
                birthDate=jane.birthDate,
                relationship=MetadataTriple(
                    identifier="SUBSCR", label="Subscriber", details="Subscriber"
                ),
                enrollment=EnrollmentDates(
                    effective="2025-01-01", termination="2025-12-31"
                ),
                status=MetadataTriple(identifier="A", label="Active", details="Active"),
                productTypes=[
                    MetadataTriple(identifier="MED", label="Medical", details="Medical")
                ],
                sequenceNumber="01",
                primaryAccountId=jane.identity.secondaryId,
                gender=MetadataTriple(identifier="F", label="Female", details="Female"),
            )
        ],
        benefitCycle="CY",
        arrangement=MetadataTriple(
            identifier="HMO", label="Health Maintenance Organization", details="HMO"
        ),
    )

    jane_elig = ContractRecord(
        identifiers=ContractIdentifiers(
            accountId=jane.identity.secondaryId,
            contractNumber="CNTR-2002",
            contractUniqueId="CONTRACT-UID-JANE-2002",
        ),
        group=GroupInfo(groupId="IND", groupName="Individual Market"),
        effectiveDate="2025-01-01",
        status=MetadataTriple(
            identifier="A", label="Active", details="Active at contract level"
        ),
        brand=MetadataTriple(
            identifier="VSTA", label="VISTA HEALTH", details="VISTA HEALTH"
        ),
        sourceSystem="ELIGSYS",
        periods=[jane_coverage_2025],
    )
    ELIGIBILITY_DB[jane.identity.primaryId] = CoveragePeriodResponse(
        eligibility=[jane_elig]
    )
    ELIGIBILITY_DB[jane.identity.secondaryId] = ELIGIBILITY_DB[jane.identity.primaryId]
    CONTRACT_UID_TO_CD["CONTRACT-UID-JANE-2002"] = "9Z9X"

    # ----- Plan Information -----

    # JOHN 2025
    PLAN_INFO_DB[(john_cov_key_2025, "MED")] = PlanInformationResponse(
        contractCd="1J1U",
        contractState="CA",
        startDt="2025-01-01",
        endDt="2025-12-31",
        marketSegment="Large Group",
        planType="Medical",
        benefitPeriod=BenefitPeriod(cd="CalendarYear", desc="Per Calendar Year"),
        valueBasedProviderInfo=ValueBasedProviderInfo(coverageFlag="Not Applicable"),
        network=[
            NetworkPlan(
                cd="ALL",
                desc="ALL",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="25",
                            unit=None,
                            desc="Choice",
                            optionNm="DEPELIGMAX",
                            optionDesc="DEPENDENT MAX AGE LIMIT",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="NEWADDBENPAY",
                            optionDesc="NEWBORN ADDED BEFORE BENEFITS PAY",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="FORCLMCOVD",
                            optionDesc="FOREIGN CLAIMS COVERED",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Unit",
                            value="12",
                            unit="Month(s)",
                            desc="Unit",
                            optionNm="CLMFILE",
                            optionDesc="CLAIM FILING LIMIT",
                        ),
                        timePeriod="From the date of service",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="COBAPPLIES",
                            optionDesc="COORDINATION OF BENEFITS APPLIES",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="TELEHLTH",
                            optionDesc="TELEHEALTH SERVICES AVAILABLE",
                        )
                    ),
                ],
            ),
            NetworkPlan(
                cd="HMO",
                desc="In Network",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="N",
                            unit=None,
                            desc="Choice",
                            optionNm="CMDRXDEDCOMB",
                            optionDesc="MED AND RX DED COMBINED",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="CMEDRXOOPCMB",
                            optionDesc="MEDICAL & RX OOP COMBINED",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Deductible",
                            value="500",
                            unit="Dollar(S)",
                            desc="Deductible",
                            optionNm="CFAMDEDDOL",
                            optionDesc="FAMILY DEDUCTIBLE",
                        ),
                        coverageLevel="Family",
                        coverageCd="FAM",
                        timePeriod="Per Calendar Year",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Deductible",
                            value="250",
                            unit="Dollar(S)",
                            desc="Deductible",
                            optionNm="CINDDEDDOL",
                            optionDesc="INDIVIDUAL DEDUCTIBLE",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Calendar Year",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="OutOfPocketMax",
                            value="3000",
                            unit="Dollar(S)",
                            desc="Out of Pocket Maximum",
                            optionNm="CFAMCOPCYMX",
                            optionDesc="FAMILY COPAY MAX",
                        ),
                        coverageLevel="Family",
                        coverageCd="FAM",
                        timePeriod="Per Calendar Year",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="OutOfPocketMax",
                            value="1500",
                            unit="Dollar(S)",
                            desc="Out of Pocket Maximum",
                            optionNm="CSNGLCOPCYMX",
                            optionDesc="SINGLE PARTY COPAY MAX",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Calendar Year",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Copay",
                            value="45",
                            unit="Dollar(S)",
                            desc="Specialist Copay",
                            optionNm="SPEC_COPAY",
                            optionDesc="SPECIALIST OFFICE VISIT COPAY",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Visit",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Copay",
                            value="75",
                            unit="Dollar(S)",
                            desc="Urgent Care Copay",
                            optionNm="URG_COPAY",
                            optionDesc="URGENT CARE FACILITY COPAY",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Visit",
                    ),
                ],
            ),
            NetworkPlan(
                cd="PAR",
                desc="Participating",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="ECONSULAPLY",
                            optionDesc="ECONSULT INTERPROFESSIONAL CONSLT APPLIES",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Coinsurance",
                            value="20",
                            unit="PCT",
                            desc="Imaging Coinsurance",
                            optionNm="IMG_COINS",
                            optionDesc="ADVANCED IMAGING COINSURANCE",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Calendar Year",
                    ),
                ],
            ),
        ],
    )

    # JOHN 2024
    PLAN_INFO_DB[(john_cov_key_2024, "MED")] = PlanInformationResponse(
        contractCd="1J1U",
        contractState="NY",
        startDt="2024-01-01",
        endDt="2024-12-31",
        marketSegment="Large Group",
        planType="Medical",
        benefitPeriod=BenefitPeriod(cd="CalendarYear", desc="Per Calendar Year"),
        valueBasedProviderInfo=ValueBasedProviderInfo(coverageFlag="Not Applicable"),
        network=[
            NetworkPlan(
                cd="INN",
                desc="In-Network",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Deductible",
                            value="1500",
                            unit="USD",
                            desc="Individual Deductible",
                        )
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Coinsurance", value="30", unit="PCT", desc="Coinsurance"
                        )
                    ),
                ],
            )
        ],
    )

    # JANE 2025
    PLAN_INFO_DB[(jane_cov_key_2025, "MED")] = PlanInformationResponse(
        contractCd="9Z9X",
        contractState="CA",
        startDt="2025-01-01",
        endDt="2025-12-31",
        marketSegment="Individual",
        planType="Medical",
        benefitPeriod=BenefitPeriod(cd="CalendarYear", desc="Per Calendar Year"),
        valueBasedProviderInfo=ValueBasedProviderInfo(coverageFlag="Not Applicable"),
        network=[
            NetworkPlan(
                cd="ALL",
                desc="ALL",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Unit",
                            value="9",
                            unit="Month(s)",
                            desc="Unit",
                            optionNm="CLMFILE",
                            optionDesc="CLAIM FILING LIMIT",
                        ),
                        coverageLevel=None,
                        coverageCd=None,
                        timePeriod="From the date of service",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Choice",
                            value="Y",
                            unit=None,
                            desc="Choice",
                            optionNm="FORCLMCOVD",
                            optionDesc="FOREIGN CLAIMS COVERED",
                        )
                    ),
                ],
            ),
            NetworkPlan(
                cd="HMO",
                desc="In Network",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Copay",
                            value="35",
                            unit="Dollar(S)",
                            desc="PCP Copay",
                            optionNm="PCP_COPAY",
                            optionDesc="PRIMARY CARE COPAY",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Visit",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Deductible",
                            value="0",
                            unit="Dollar(S)",
                            desc="Deductible",
                            optionNm="CINDDEDDOL",
                            optionDesc="INDIVIDUAL DEDUCTIBLE",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Calendar Year",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="OutOfPocketMax",
                            value="4500",
                            unit="Dollar(S)",
                            desc="Out of Pocket Maximum",
                            optionNm="CSNGLCOPCYMX",
                            optionDesc="SINGLE PARTY COPAY MAX",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Calendar Year",
                    ),
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Copay",
                            value="10",
                            unit="Dollar(S)",
                            desc="Generic Rx Copay",
                            optionNm="RX_GEN_COPAY",
                            optionDesc="GENERIC PRESCRIPTION COPAY",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Fill",
                    ),
                ],
            ),
            NetworkPlan(
                cd="PAR",
                desc="Participating",
                costShare=[
                    CostShareEntry(
                        benefit=BenefitItem(
                            cd="Coinsurance",
                            value="30",
                            unit="PCT",
                            desc="Outpatient Surgery Coinsurance",
                            optionNm="OPS_COINS",
                            optionDesc="OUTPATIENT SURGERY COINSURANCE",
                        ),
                        coverageLevel="Individual",
                        coverageCd="IND",
                        timePeriod="Per Calendar Year",
                    ),
                ],
            ),
        ],
    )

    return ELIGIBILITY_DB, COVERAGE_KEY_INDEX, PLAN_INFO_DB, CONTRACT_UID_TO_CD


# =====================================================
# Benefit search builders
# =====================================================


def _pos_all() -> List[POS]:
    return [POS(posCd=None, posDesc="ALL")]


def _pos_office() -> List[POS]:
    return [POS(posCd="11", posDesc="Office")]


def build_emergency_er(
    contract_uid: str, contract_cd: str, effective_mmddyyyy: str, doc_id: str, mcid: str
) -> CoverageInquiryResult:
    return CoverageInquiryResult(
        context=InquiryContext(
            memberId=mcid,
            contractReference=contract_uid,
            contractCode=contract_cd,
            documentId=doc_id,
            effectiveDate=effective_mmddyyyy,
            searchQuery="Injury",
        ),
        categories=[
            ProductCategory(
                planType="Medical",
                categories=[
                    CategoryEntry(
                        services=[
                            ServiceEntry(
                                categoryNm="Emergency Care",
                                benefits=[
                                    CoverageSpecification(
                                        specificationName="Emergency - Emergency Room (Institutional)",
                                        category="Emergency - Emergency Room",
                                        applicableSettings=["Institutional"],
                                        systemIdentifier="82da10ab-c05d-46e1-bf48-ad61ea70eb3d",
                                        scenarios=[
                                            CoverageScenario(
                                                pos=_pos_all(),
                                                networks=[
                                                    NetworkCostStructure(
                                                        networkCode="INN",
                                                        networkLabel="In Network",
                                                        deductibleRequired="Yes",
                                                        priorAuthRequired="N",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="0%",
                                                            ),
                                                            CostComponent(
                                                                type="Copayment",
                                                                value="$400 Per Visit",
                                                            ),
                                                        ],
                                                    ),
                                                    NetworkCostStructure(
                                                        networkCode="OON",
                                                        networkLabel="Out of Network",
                                                        deductibleRequired="Covered - At the INN benefit level",
                                                        priorAuthRequired="N",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="Covered - At the INN benefit level",
                                                            ),
                                                            CostComponent(
                                                                type="Copayment",
                                                                value="Covered - At the INN benefit level",
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ]
                    )
                ],
            )
        ],
        relatedProcedures=None,
    )


def build_office_visits(
    contract_uid: str, contract_cd: str, effective_mmddyyyy: str, doc_id: str, mcid: str
) -> CoverageInquiryResult:
    return CoverageInquiryResult(
        context=InquiryContext(
            memberId=mcid,
            contractReference=contract_uid,
            contractCode=contract_cd,
            documentId=doc_id,
            effectiveDate=effective_mmddyyyy,
            searchQuery="Office Visit",
        ),
        categories=[
            ProductCategory(
                planType="Medical",
                categories=[
                    CategoryEntry(
                        services=[
                            ServiceEntry(
                                categoryNm="Professional Physician Services",
                                benefits=[
                                    CoverageSpecification(
                                        specificationName="Office Visits Outpatient Professional - PCP",
                                        category="Office Visits",
                                        applicableSettings=["Outpatient Professional"],
                                        systemIdentifier="pcp-ov-11",
                                        scenarios=[
                                            CoverageScenario(
                                                pos=_pos_office(),
                                                networks=[
                                                    NetworkCostStructure(
                                                        networkCode="INN",
                                                        networkLabel="In Network",
                                                        deductibleRequired="No",
                                                        priorAuthRequired="N",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="0%",
                                                            ),
                                                            CostComponent(
                                                                type="Copayment",
                                                                value="$25 Per Visit",
                                                            ),
                                                        ],
                                                    )
                                                ],
                                            )
                                        ],
                                    ),
                                    CoverageSpecification(
                                        specificationName="Office Visits Outpatient Professional - Specialist",
                                        category="Office Visits",
                                        applicableSettings=["Outpatient Professional"],
                                        systemIdentifier="spec-ov-11",
                                        scenarios=[
                                            CoverageScenario(
                                                pos=_pos_office(),
                                                networks=[
                                                    NetworkCostStructure(
                                                        networkCode="INN",
                                                        networkLabel="In Network",
                                                        deductibleRequired="No",
                                                        priorAuthRequired="N",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="0%",
                                                            ),
                                                            CostComponent(
                                                                type="Copayment",
                                                                value="$55 Per Visit",
                                                            ),
                                                        ],
                                                    )
                                                ],
                                            )
                                        ],
                                    ),
                                ],
                            )
                        ]
                    )
                ],
            )
        ],
        relatedProcedures=None,
    )


def build_mri(
    contract_uid: str, contract_cd: str, effective_mmddyyyy: str, doc_id: str, mcid: str
) -> CoverageInquiryResult:
    return CoverageInquiryResult(
        context=InquiryContext(
            memberId=mcid,
            contractReference=contract_uid,
            contractCode=contract_cd,
            documentId=doc_id,
            effectiveDate=effective_mmddyyyy,
            searchQuery="MRI",
        ),
        categories=[
            ProductCategory(
                planType="Medical",
                categories=[
                    CategoryEntry(
                        services=[
                            ServiceEntry(
                                categoryNm="Diagnostic Services",
                                benefits=[
                                    CoverageSpecification(
                                        specificationName="MRI (Magnetic Resonance Imaging)",
                                        category="Imaging",
                                        applicableSettings=[
                                            "Outpatient Hospital",
                                            "Freestanding Facility",
                                        ],
                                        systemIdentifier="mri-IMG-OP",
                                        scenarios=[
                                            CoverageScenario(
                                                pos=_pos_all(),
                                                networks=[
                                                    NetworkCostStructure(
                                                        networkCode="INN",
                                                        networkLabel="In Network",
                                                        deductibleRequired="Yes",
                                                        priorAuthRequired="Y",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="20%",
                                                            ),
                                                            CostComponent(
                                                                type="Copayment",
                                                                value="$0",
                                                            ),
                                                        ],
                                                    ),
                                                    NetworkCostStructure(
                                                        networkCode="OON",
                                                        networkLabel="Out of Network",
                                                        deductibleRequired="Yes",
                                                        priorAuthRequired="N",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="40%",
                                                            )
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ]
                    )
                ],
            )
        ],
        relatedProcedures=[
            RelatedProcedure(code="CPT:70551", name="MRI brain without contrast")
        ],
    )


def build_knee_surgery(
    contract_uid: str, contract_cd: str, effective_mmddyyyy: str, doc_id: str, mcid: str
) -> CoverageInquiryResult:
    return CoverageInquiryResult(
        context=InquiryContext(
            memberId=mcid,
            contractReference=contract_uid,
            contractCode=contract_cd,
            documentId=doc_id,
            effectiveDate=effective_mmddyyyy,
            searchQuery="Knee Surgery",
        ),
        categories=[
            ProductCategory(
                planType="Medical",
                categories=[
                    CategoryEntry(
                        services=[
                            ServiceEntry(
                                categoryNm="Surgical Services",
                                benefits=[
                                    CoverageSpecification(
                                        specificationName="Outpatient Surgery - Knee",
                                        category="Surgery",
                                        applicableSettings=[
                                            "Ambulatory Surgical Center",
                                            "Outpatient Hospital",
                                        ],
                                        systemIdentifier="knee-surg-op",
                                        scenarios=[
                                            CoverageScenario(
                                                pos=_pos_all(),
                                                networks=[
                                                    NetworkCostStructure(
                                                        networkCode="INN",
                                                        networkLabel="In Network",
                                                        deductibleRequired="Yes",
                                                        priorAuthRequired="Y",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="20% after deductible",
                                                            )
                                                        ],
                                                    ),
                                                    NetworkCostStructure(
                                                        networkCode="OON",
                                                        networkLabel="Out of Network",
                                                        deductibleRequired="Yes",
                                                        priorAuthRequired="Y",
                                                        costComponents=[
                                                            CostComponent(
                                                                type="Coinsurance",
                                                                value="40% after deductible",
                                                            )
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ]
                    )
                ],
            )
        ],
        relatedProcedures=[RelatedProcedure(code="CPT:29881", name="Knee arthroscopy")],
    )


SUPPORTED_BENEFIT_INTENTS = {
    "knee injury": build_emergency_er,
    "office visit": build_office_visits,
    "mri": build_mri,
    "knee surgery": build_knee_surgery,
}


# ============ Benefit Details ============


def _detail_pos_all() -> List[DetailPOS]:
    return [DetailPOS(posCd=None, posDesc="ALL")]


def _detail_pos_office() -> List[DetailPOS]:
    return [DetailPOS(posCd="11", posDesc="Office")]


def _plan_level_inn_copay_coins(
    copay: str, coins: str
) -> List[DetailNetworkCostStructure]:
    return [
        DetailNetworkCostStructure(
            code="INN",
            type="In Network",
            deductibleApplies="Depends on benefit",
            precertRequired="N",
            costshares=[
                DetailCostComponent(type="Copayment", value=copay),
                DetailCostComponent(type="Coinsurance", value=coins),
            ],
        )
    ]


# BENEFIT_DETAILS_DB key: (contract_uid, benefit_sys_id)
BENEFIT_DETAILS_DB: Dict[tuple, Dict] = {
    # Emergency Room (Institutional)
    ("CONTRACT-UID-JOHN-1001", "82da10ab-c05d-46e1-bf48-ad61ea70eb3d"): {
        "serviceCategory": [
            ServiceCategoryDetails(
                planType="Medical",
                services=[
                    ServiceDetailsGroup(
                        categoryNm="Emergency Care",
                        service=[
                            ServiceBenefitDetail(
                                benefitNm="Emergency - Emergency Room (Institutional)",
                                benefitType="Emergency - Emergency Room",
                                specialtyType=["Institutional"],
                                srvcDefnId=["82da10ab-c05d-46e1-bf48-ad61ea70eb3d"],
                                situations=[
                                    DetailCoverageScenario(
                                        pos=_detail_pos_all(),
                                        diagnosisCd=["S86.911A", "T14.90XA"],
                                        networks=[
                                            DetailNetworkCostStructure(
                                                code="INN",
                                                type="In Network",
                                                deductibleApplies="Yes",
                                                precertRequired="N",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Copayment",
                                                        value="$400 Per Visit",
                                                    ),
                                                    DetailCostComponent(
                                                        type="Coinsurance", value="0%"
                                                    ),
                                                ],
                                            ),
                                            DetailNetworkCostStructure(
                                                code="OON",
                                                type="Out of Network",
                                                deductibleApplies="Covered - At the INN benefit level",
                                                precertRequired="N",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Copayment",
                                                        value="Covered - At the INN benefit level",
                                                    ),
                                                    DetailCostComponent(
                                                        type="Coinsurance",
                                                        value="Covered - At the INN benefit level",
                                                    ),
                                                ],
                                            ),
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
        "planLevel": [
            PlanLevelEntry(
                planType="Medical",
                benefits=[
                    PlanLevelBenefitsGroup(
                        networks=_plan_level_inn_copay_coins("$400 Per Visit", "0%")
                    )
                ],
            )
        ],
    },
    # Office Visits - PCP
    ("CONTRACT-UID-JOHN-1001", "pcp-ov-11"): {
        "serviceCategory": [
            ServiceCategoryDetails(
                planType="Medical",
                services=[
                    ServiceDetailsGroup(
                        categoryNm="Professional Physician Services",
                        service=[
                            ServiceBenefitDetail(
                                benefitNm="Office Visits Outpatient Professional - PCP",
                                benefitType="Office Visits",
                                specialtyType=["Outpatient Professional"],
                                srvcDefnId=["pcp-ov-11"],
                                situations=[
                                    DetailCoverageScenario(
                                        pos=_detail_pos_office(),
                                        diagnosisCd=["Z00.00", "J01.90"],
                                        networks=[
                                            DetailNetworkCostStructure(
                                                code="INN",
                                                type="In Network",
                                                deductibleApplies="No",
                                                precertRequired="N",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Copayment",
                                                        value="$25 Per Visit",
                                                    ),
                                                    DetailCostComponent(
                                                        type="Coinsurance", value="0%"
                                                    ),
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
        "planLevel": [
            PlanLevelEntry(
                planType="Medical",
                benefits=[
                    PlanLevelBenefitsGroup(
                        networks=_plan_level_inn_copay_coins("$25 Per Visit", "0%")
                    )
                ],
            )
        ],
    },
    # Office Visits - Specialist
    ("CONTRACT-UID-JOHN-1001", "spec-ov-11"): {
        "serviceCategory": [
            ServiceCategoryDetails(
                planType="Medical",
                services=[
                    ServiceDetailsGroup(
                        categoryNm="Professional Physician Services",
                        service=[
                            ServiceBenefitDetail(
                                benefitNm="Office Visits Outpatient Professional - Specialist",
                                benefitType="Office Visits",
                                specialtyType=["Outpatient Professional"],
                                srvcDefnId=["spec-ov-11"],
                                situations=[
                                    DetailCoverageScenario(
                                        pos=_detail_pos_office(),
                                        diagnosisCd=["M25.50"],
                                        networks=[
                                            DetailNetworkCostStructure(
                                                code="INN",
                                                type="In Network",
                                                deductibleApplies="No",
                                                precertRequired="N",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Copayment",
                                                        value="$55 Per Visit",
                                                    ),
                                                    DetailCostComponent(
                                                        type="Coinsurance", value="0%"
                                                    ),
                                                ],
                                            )
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
        "planLevel": [
            PlanLevelEntry(
                planType="Medical",
                benefits=[
                    PlanLevelBenefitsGroup(
                        networks=_plan_level_inn_copay_coins("$55 Per Visit", "0%")
                    )
                ],
            )
        ],
    },
    # MRI
    ("CONTRACT-UID-JOHN-1001", "mri-IMG-OP"): {
        "serviceCategory": [
            ServiceCategoryDetails(
                planType="Medical",
                services=[
                    ServiceDetailsGroup(
                        categoryNm="Diagnostic Services",
                        service=[
                            ServiceBenefitDetail(
                                benefitNm="MRI (Magnetic Resonance Imaging)",
                                benefitType="Imaging",
                                specialtyType=[
                                    "Outpatient Hospital",
                                    "Freestanding Facility",
                                ],
                                srvcDefnId=["mri-IMG-OP"],
                                situations=[
                                    DetailCoverageScenario(
                                        pos=_detail_pos_all(),
                                        diagnosisCd=["R51", "G44.209"],
                                        networks=[
                                            DetailNetworkCostStructure(
                                                code="INN",
                                                type="In Network",
                                                deductibleApplies="Yes",
                                                precertRequired="Y",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Coinsurance", value="20%"
                                                    ),
                                                    DetailCostComponent(
                                                        type="Copayment", value="$0"
                                                    ),
                                                ],
                                            ),
                                            DetailNetworkCostStructure(
                                                code="OON",
                                                type="Out of Network",
                                                deductibleApplies="Yes",
                                                precertRequired="N",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Coinsurance", value="40%"
                                                    )
                                                ],
                                            ),
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
        "planLevel": [
            PlanLevelEntry(
                planType="Medical",
                benefits=[
                    PlanLevelBenefitsGroup(
                        networks=[
                            DetailNetworkCostStructure(
                                code="INN",
                                type="In Network",
                                deductibleApplies="Yes",
                                precertRequired="Y",
                                costshares=[
                                    DetailCostComponent(type="Coinsurance", value="20%")
                                ],
                            )
                        ]
                    )
                ],
            )
        ],
    },
    # Knee Surgery (Outpatient)
    ("CONTRACT-UID-JOHN-1001", "knee-surg-op"): {
        "serviceCategory": [
            ServiceCategoryDetails(
                planType="Medical",
                services=[
                    ServiceDetailsGroup(
                        categoryNm="Surgical Services",
                        service=[
                            ServiceBenefitDetail(
                                benefitNm="Outpatient Surgery - Knee",
                                benefitType="Surgery",
                                specialtyType=[
                                    "Ambulatory Surgical Center",
                                    "Outpatient Hospital",
                                ],
                                srvcDefnId=["knee-surg-op"],
                                situations=[
                                    DetailCoverageScenario(
                                        pos=_detail_pos_all(),
                                        diagnosisCd=["M23.91", "S83.241A"],
                                        networks=[
                                            DetailNetworkCostStructure(
                                                code="INN",
                                                type="In Network",
                                                deductibleApplies="Yes",
                                                precertRequired="Y",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Coinsurance",
                                                        value="20% after deductible",
                                                    )
                                                ],
                                            ),
                                            DetailNetworkCostStructure(
                                                code="OON",
                                                type="Out of Network",
                                                deductibleApplies="Yes",
                                                precertRequired="Y",
                                                costshares=[
                                                    DetailCostComponent(
                                                        type="Coinsurance",
                                                        value="40% after deductible",
                                                    )
                                                ],
                                            ),
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
        "planLevel": [
            PlanLevelEntry(
                planType="Medical",
                benefits=[
                    PlanLevelBenefitsGroup(
                        networks=[
                            DetailNetworkCostStructure(
                                code="INN",
                                type="In Network",
                                deductibleApplies="Yes",
                                precertRequired="Y",
                                costshares=[
                                    DetailCostComponent(
                                        type="Coinsurance", value="20% after deductible"
                                    )
                                ],
                            )
                        ]
                    )
                ],
            )
        ],
    },
}

# (Optional) mirror of the above for JANE's contract:
for _sys in [
    "82da10ab-c05d-46e1-bf48-ad61ea70eb3d",
    "pcp-ov-11",
    "spec-ov-11",
    "mri-IMG-OP",
    "knee-surg-op",
]:
    if ("CONTRACT-UID-JANE-2002", _sys) not in BENEFIT_DETAILS_DB:
        BENEFIT_DETAILS_DB[("CONTRACT-UID-JANE-2002", _sys)] = BENEFIT_DETAILS_DB[
            ("CONTRACT-UID-JOHN-1001", _sys)
        ]

# ============ Provider Directory ============

PROVIDERS_DB: List[CareProviderProfile] = [
    CareProviderProfile(
        providerId="PRV-0001",
        name="Ethan Cole",
        address=LocationDetails(
            facilityName="Acme Primary Care Clinic",
            locationId="ADDR-0001",
            address=AddressComponents(
                line1="100 Wellness Way",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11211",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(
                phone="+1-212-555-0101", email="frontdesk@acme-pcc.example"
            ),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                ),
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                ),
            ],
            specialtyCategories=["25"],  # Family/General Practice
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0002",
        name="Sophia Ramirez",
        address=LocationDetails(
            facilityName="Vista Radiology Center",
            locationId="ADDR-0002",
            address=AddressComponents(
                line1="500 Imaging Blvd",
                line2="Suite 200",
                city="Queens",
                stateCode="NY",
                zipCode="11373",
                county="Queens",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-0202", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QR0200X",
                    name="Radiology Clinic/Center",
                    description="Clinic/Center - Radiology",
                ),
                ProviderTaxonomy(
                    code="2085R0202X",
                    name="Radiology, Diagnostic",
                    description="Radiology - Diagnostic",
                ),
            ],
            specialtyCategories=["231", "75"],  # Clinics/Radiology, Imaging centers
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=True, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0003",
        name="Liam Bennett",
        address=LocationDetails(
            facilityName="Northside Orthopedic Group",
            locationId="ADDR-0003",
            address=AddressComponents(
                line1="250 Ortho Park",
                line2=None,
                city="New York",
                stateCode="NY",
                zipCode="10024",
                county="New York",
                country="US",
            ),
            contact=ContactInfo(
                phone="+1-212-555-0303", email="contact@north-ortho.example"
            ),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="207X00000X",
                    name="Orthopedic Surgery",
                    description="Allopathic & Osteopathic Physicians - Orthopaedic Surgery",
                ),
            ],
            specialtyCategories=["220"],  # e.g., Surgery/Ortho (mock)
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0004",
        name="Olivia Carter",
        address=LocationDetails(
            facilityName="Harbor Community Health",
            locationId="ADDR-0004",
            address=AddressComponents(
                line1="75 Harbor St",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11217",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-0404", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                ),
            ],
            specialtyCategories=["25", "231"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0101",
        name="Noah Sullivan",
        address=LocationDetails(
            facilityName="Greenpoint Family Practice",
            locationId="ADDR-0101",
            address=AddressComponents(
                line1="101 Green Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11222",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1101", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=True, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0102",
        name="Ava Thompson",
        address=LocationDetails(
            facilityName="Bedford Primary Care",
            locationId="ADDR-0102",
            address=AddressComponents(
                line1="202 Bedford Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11249",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1102", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                ),
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                ),
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=True, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0103",
        name="Mason Brooks",
        address=LocationDetails(
            facilityName="Cobble Hill Medical Group",
            locationId="ADDR-0103",
            address=AddressComponents(
                line1="303 Court St",
                line2="Suite 2",
                city="Brooklyn",
                stateCode="NY",
                zipCode="11231",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1103", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0104",
        name="Isabella Hayes",
        address=LocationDetails(
            facilityName="Brooklyn Heights Family Health",
            locationId="ADDR-0104",
            address=AddressComponents(
                line1="88 Montague St",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11201",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1104", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0105",
        name="Lucas Parker",
        address=LocationDetails(
            facilityName="Williamsburg Family Medicine",
            locationId="ADDR-0105",
            address=AddressComponents(
                line1="120 Havemeyer St",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11211",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1105", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=True, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0106",
        name="Charlotte Reed",
        address=LocationDetails(
            facilityName="Park Slope Primary Care",
            locationId="ADDR-0106",
            address=AddressComponents(
                line1="400 7th Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11215",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1106", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=True, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0107",
        name="James Foster",
        address=LocationDetails(
            facilityName="Prospect Heights Family Care",
            locationId="ADDR-0107",
            address=AddressComponents(
                line1="55 Vanderbilt Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11238",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1107", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=True, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0108",
        name="Amelia Collins",
        address=LocationDetails(
            facilityName="Downtown Brooklyn Health",
            locationId="ADDR-0108",
            address=AddressComponents(
                line1="2 MetroTech Center",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11201",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1108", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0109",
        name="Henry Mitchell",
        address=LocationDetails(
            facilityName="Fort Greene Family Practice",
            locationId="ADDR-0109",
            address=AddressComponents(
                line1="141 Greene Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11238",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1109", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0110",
        name="Emily Sanders",
        address=LocationDetails(
            facilityName="Clinton Hill Primary Care",
            locationId="ADDR-0110",
            address=AddressComponents(
                line1="85 Waverly Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11205",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1110", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0111",
        name="Alexander Ward",
        address=LocationDetails(
            facilityName="Sunset Park Family Health",
            locationId="ADDR-0111",
            address=AddressComponents(
                line1="800 5th Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11232",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1111", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="207Q00000X",
                    name="Family Medicine",
                    description="Allopathic & Osteopathic Physicians - Family Medicine",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
    CareProviderProfile(
        providerId="PRV-0112",
        name="Grace Morgan",
        address=LocationDetails(
            facilityName="Bushwick Primary Care",
            locationId="ADDR-0112",
            address=AddressComponents(
                line1="900 Bushwick Ave",
                line2=None,
                city="Brooklyn",
                stateCode="NY",
                zipCode="11221",
                county="Kings",
                country="US",
            ),
            contact=ContactInfo(phone="+1-718-555-1112", email=None),
            coordinates=GeoCoordinates(distanceMiles=0.0),
        ),
        expertise=ExpertiseProfile(
            taxonomies=[
                ProviderTaxonomy(
                    code="261QP2300X",
                    name="Primary Care Clinic",
                    description="Clinic/Center - Primary Care",
                )
            ],
            specialtyCategories=["25"],
        ),
        network=NetworkParticipation(
            status="TP_INNETWORK", accept_new_patients=False, coverages=["MED"]
        ),
    ),
]

# ====== Suggestions seeds ======

SUGGESTIONS_DB = {
    # SPECIALTY: Primary Care / Family Practice
    "primary care": [
        SuggestionItem(
            text="Primary Care Doctor near me",
            type="SPECIALTY",
            score=0.96,
            criteria=SuggestionCriteria(
                taxonomyList=[
                    ProviderTaxonomy(
                        code="261QP2300X",
                        name="Primary Care Clinic",
                        description="Clinic/Center - Primary Care",
                    ),
                    ProviderTaxonomy(
                        code="207Q00000X",
                        name="Family Medicine",
                        description="Allopathic & Osteopathic Physicians - Family Medicine",
                    ),
                ],
                specialtyCategoryList=[
                    MetadataTriple(
                        identifier="25",
                        label="Family/General Practice",
                        details="Primary care / family practice",
                    )
                ],
            ),
            procedureCode=None,
            medicalCode=None,
            metaData={},
            dplQueryParams={
                "specialty_category_codes": "25",
                "taxonomy_codes": "261QP2300X,207Q00000X",
                "distance": "20",
                "page_index": "0",
                "size": "5",
            },
        ),
    ],
    # SPECIALTY: Imaging / Radiology
    "radiology": [
        SuggestionItem(
            text="Radiology Clinic or Imaging Center",
            type="SPECIALTY",
            score=0.92,
            criteria=SuggestionCriteria(
                taxonomyList=[
                    ProviderTaxonomy(
                        code="261QR0200X",
                        name="Radiology Clinic/Center",
                        description="Clinic/Center - Radiology",
                    ),
                    ProviderTaxonomy(
                        code="2085R0202X",
                        name="Radiology, Diagnostic",
                        description="Radiology - Diagnostic",
                    ),
                ],
                specialtyCategoryList=[
                    MetadataTriple(
                        identifier="231",
                        label="Clinics / Radiology",
                        details="Clinics / Radiology",
                    ),
                    MetadataTriple(
                        identifier="75",
                        label="Imaging Centers",
                        details="Imaging Centers",
                    ),
                ],
            ),
            procedureCode=None,
            medicalCode=None,
            metaData={},
            dplQueryParams={
                "specialty_category_codes": "231,75",
                "taxonomy_codes": "261QR0200X,2085R0202X",
                "distance": "30",
                "page_index": "0",
                "size": "5",
            },
        ),
    ],
    # PROCEDURE: MRI
    "mri": [
        SuggestionItem(
            text="MRI (Magnetic Resonance Imaging)",
            type="PROCEDURE",
            score=0.9,
            criteria=SuggestionCriteria(
                taxonomyList=[
                    ProviderTaxonomy(
                        code="261QR0200X",
                        name="Radiology Clinic/Center",
                        description="Clinic/Center - Radiology",
                    )
                ],
                specialtyCategoryList=[
                    MetadataTriple(
                        identifier="75",
                        label="Imaging Centers",
                        details="Imaging Centers",
                    )
                ],
            ),
            procedureCode="MRI",
            medicalCode="IMG-MRI",
            metaData={},
            dplQueryParams={
                "specialty_category_codes": "75",
                "taxonomy_codes": "261QR0200X",
                "distance": "30",
                "page_index": "0",
                "size": "5",
            },
        ),
    ],
    # PROCEDURE: Knee Surgery (orthopedics)
    "knee surgery": [
        SuggestionItem(
            text="Orthopedic Surgeon - Knee Surgery",
            type="PROCEDURE",
            score=0.91,
            criteria=SuggestionCriteria(
                taxonomyList=[
                    ProviderTaxonomy(
                        code="207X00000X",
                        name="Orthopedic Surgery",
                        description="Allopathic & Osteopathic Physicians - Orthopaedic Surgery",
                    )
                ],
                specialtyCategoryList=[
                    MetadataTriple(
                        identifier="220",
                        label="Surgery / Orthopedics",
                        details="Orthopedic Surgery",
                    )
                ],
            ),
            procedureCode="CPT:29881",
            medicalCode="KNEE-ARTHROSCOPY",
            metaData={},
            dplQueryParams={
                "specialty_category_codes": "220",
                "taxonomy_codes": "207X00000X",
                "distance": "25",
                "page_index": "0",
                "size": "5",
            },
        ),
    ],
}

# ====== Medical KB seeds (paginated) ======


def _ct(en_us: str, en_ca: str, es_us: str) -> ConsumerText:
    return ConsumerText(consumer={"en-us": en_us, "en-ca": en_ca, "es-us": es_us})


MEDICAL_KB = {
    # Hypertension: 8 articles (pagination needed)
    "high blood pressure": [
        MedicalArticle(
            id="htn-001",
            url="https://example.health/articles/htn-overview",
            title=_ct(
                "High Blood Pressure: Overview",
                "High Blood Pressure: Overview",
                "Presión arterial alta: Descripción general",
            ),
            abstract=_ct(
                "What hypertension is and why it matters.",
                "What hypertension is and why it matters.",
                "Qué es la hipertensión y por qué importa.",
            ),
        ),
        MedicalArticle(
            id="htn-002",
            url="https://example.health/articles/htn-symptoms",
            title=_ct(
                "Hypertension Symptoms",
                "Hypertension Symptoms",
                "Síntomas de la hipertensión",
            ),
            abstract=_ct(
                "Common and uncommon symptoms.",
                "Common and uncommon symptoms.",
                "Síntomas comunes e inusuales.",
            ),
        ),
        MedicalArticle(
            id="htn-003",
            url="https://example.health/articles/htn-causes",
            title=_ct(
                "Causes of High Blood Pressure",
                "Causes of High Blood Pressure",
                "Causas de la presión arterial alta",
            ),
            abstract=_ct(
                "Genetics, lifestyle, and other factors.",
                "Genetics, lifestyle, and other factors.",
                "Genética, estilo de vida y otros factores.",
            ),
        ),
        MedicalArticle(
            id="htn-004",
            url="https://example.health/articles/htn-diagnosis",
            title=_ct(
                "Diagnosing Hypertension",
                "Diagnosing Hypertension",
                "Diagnóstico de la hipertensión",
            ),
            abstract=_ct(
                "How doctors measure and confirm hypertension.",
                "How doctors measure and confirm hypertension.",
                "Cómo los médicos miden y confirman la hipertensión.",
            ),
        ),
        MedicalArticle(
            id="htn-005",
            url="https://example.health/articles/htn-treatment",
            title=_ct(
                "Treatment Options for Hypertension",
                "Treatment Options for Hypertension",
                "Opciones de tratamiento para la hipertensión",
            ),
            abstract=_ct(
                "Medications, diet, and exercise.",
                "Medications, diet, and exercise.",
                "Medicamentos, dieta y ejercicio.",
            ),
        ),
        MedicalArticle(
            id="htn-006",
            url="https://example.health/articles/htn-lifestyle",
            title=_ct(
                "Lifestyle Changes to Lower BP",
                "Lifestyle Changes to Lower BP",
                "Cambios de estilo de vida para bajar la presión",
            ),
            abstract=_ct(
                "Dietary patterns, sodium, and activity.",
                "Dietary patterns, sodium, and activity.",
                "Dieta, sodio y actividad.",
            ),
        ),
        MedicalArticle(
            id="htn-007",
            url="https://example.health/articles/htn-complications",
            title=_ct(
                "Complications of High Blood Pressure",
                "Complications of High Blood Pressure",
                "Complicaciones de la presión arterial alta",
            ),
            abstract=_ct(
                "Heart disease, stroke, and kidney damage.",
                "Heart disease, stroke, and kidney damage.",
                "Cardiopatía, ictus y daño renal.",
            ),
        ),
        MedicalArticle(
            id="htn-008",
            url="https://example.health/articles/htn-monitoring",
            title=_ct(
                "Monitoring Your Blood Pressure at Home",
                "Monitoring Your Blood Pressure at Home",
                "Monitoreo de la presión arterial en casa",
            ),
            abstract=_ct(
                "Devices and best practices.",
                "Devices and best practices.",
                "Dispositivos y mejores prácticas.",
            ),
        ),
    ],
    # Diabetes: 6 articles (pagination needed)
    "diabetes": [
        MedicalArticle(
            id="dm-001",
            url="https://example.health/articles/diabetes-overview",
            title=_ct(
                "Diabetes: Overview",
                "Diabetes: Overview",
                "Diabetes: Descripción general",
            ),
            abstract=_ct(
                "Types 1 and 2, and prediabetes.",
                "Types 1 and 2, and prediabetes.",
                "Tipos 1 y 2, y prediabetes.",
            ),
        ),
        MedicalArticle(
            id="dm-002",
            url="https://example.health/articles/diabetes-symptoms",
            title=_ct(
                "Diabetes Symptoms", "Diabetes Symptoms", "Síntomas de la diabetes"
            ),
            abstract=_ct(
                "Common signs and when to see a doctor.",
                "Common signs and when to see a doctor.",
                "Señales comunes y cuándo ver a un médico.",
            ),
        ),
        MedicalArticle(
            id="dm-003",
            url="https://example.health/articles/diabetes-management",
            title=_ct(
                "Managing Diabetes", "Managing Diabetes", "Manejo de la diabetes"
            ),
            abstract=_ct(
                "Monitoring glucose, diet, and medications.",
                "Monitoring glucose, diet, and medications.",
                "Control de glucosa, dieta y medicamentos.",
            ),
        ),
        MedicalArticle(
            id="dm-004",
            url="https://example.health/articles/diabetes-complications",
            title=_ct(
                "Complications of Diabetes",
                "Complications of Diabetes",
                "Complicaciones de la diabetes",
            ),
            abstract=_ct(
                "Eyes, nerves, kidneys, and heart.",
                "Eyes, nerves, kidneys, and heart.",
                "Ojos, nervios, riñones y corazón.",
            ),
        ),
        MedicalArticle(
            id="dm-005",
            url="https://example.health/articles/diabetes-exercise",
            title=_ct(
                "Exercise and Diabetes", "Exercise and Diabetes", "Ejercicio y diabetes"
            ),
            abstract=_ct(
                "How activity helps manage blood sugar.",
                "How activity helps manage blood sugar.",
                "Cómo la actividad ayuda a controlar el azúcar.",
            ),
        ),
        MedicalArticle(
            id="dm-006",
            url="https://example.health/articles/diabetes-diet",
            title=_ct(
                "Diet for Diabetes", "Diet for Diabetes", "Dieta para la diabetes"
            ),
            abstract=_ct(
                "Carbs, fiber, and meal planning.",
                "Carbs, fiber, and meal planning.",
                "Carbohidratos, fibra y planificación de comidas.",
            ),
        ),
    ],
    # Knee Surgery: 4 articles (no pagination needed)
    "knee surgery": [
        MedicalArticle(
            id="knee-001",
            url="https://example.health/articles/knee-prep",
            title=_ct(
                "Preparing for Knee Surgery",
                "Preparing for Knee Surgery",
                "Preparación para la cirugía de rodilla",
            ),
            abstract=_ct(
                "Pre-op guidance and expectations.",
                "Pre-op guidance and expectations.",
                "Guía preoperatoria y expectativas.",
            ),
        ),
        MedicalArticle(
            id="knee-002",
            url="https://example.health/articles/knee-types",
            title=_ct(
                "Types of Knee Surgery",
                "Types of Knee Surgery",
                "Tipos de cirugía de rodilla",
            ),
            abstract=_ct(
                "Arthroscopy, partial, and total replacement.",
                "Arthroscopy, partial, and total replacement.",
                "Artroscopia, parcial y reemplazo total.",
            ),
        ),
        MedicalArticle(
            id="knee-003",
            url="https://example.health/articles/knee-recovery",
            title=_ct(
                "Knee Surgery Recovery",
                "Knee Surgery Recovery",
                "Recuperación de cirugía de rodilla",
            ),
            abstract=_ct(
                "Rehab timelines and pain control.",
                "Rehab timelines and pain control.",
                "Tiempos de rehabilitación y control del dolor.",
            ),
        ),
        MedicalArticle(
            id="knee-004",
            url="https://example.health/articles/knee-risks",
            title=_ct(
                "Risks of Knee Surgery",
                "Risks of Knee Surgery",
                "Riesgos de la cirugía de rodilla",
            ),
            abstract=_ct(
                "Complications and how to reduce them.",
                "Complications and how to reduce them.",
                "Complicaciones y cómo reducirlas.",
            ),
        ),
    ],
}

# ===== Billing ledger (by clmUid) =====
# status: DUE | PAID | PARTIAL | IN_COLLECTIONS
BILLING_LEDGER: Dict[str, Dict[str, str]] = {
    # Some JOHN claims
    "63FA69DB119C2E16E21B487BC411E1F2": {
        "status": "DUE",
        "dueAmt": "10.00",
        "dueDt": "2025-03-15",
    },
    "9C0C8D7A6B5A4899BC12EF3344CDA123": {
        "status": "PAID",
        "dueAmt": "0.00",
        "dueDt": "2025-02-25",
    },
    "9C0C8D7A6B5A4899BC12EF3344CDA456": {
        "status": "IN_COLLECTIONS",
        "dueAmt": "80.00",
        "dueDt": "2025-04-10",
    },
    # SARA
    "9C0C8D7A6B5A499BA3A4F33AQW1DA211": {
        "status": "DUE",
        "dueAmt": "60.00",
        "dueDt": "2025-03-10",
    },
    # TOM
    "9C0C8Q1A6B28499BA3A2333AQW1DAADE": {
        "status": "DUE",
        "dueAmt": "95.00",
        "dueDt": "2025-03-12",
    },
    "9C0C8D7A6B5A4899BA3A4F3344CDA451": {
        "status": "DUE",
        "dueAmt": "15.00",
        "dueDt": "2025-03-20",
    },
    # JANE
    "C3333333333333333333333333333333": {
        "status": "DUE",
        "dueAmt": "50.00",
        "dueDt": "2025-03-18",
    },
}

# ===== Payment intents (runtime) =====
PAYMENT_INTENTS: Dict[str, Dict[str, str]] = {
    # Example structure:
    # "pi_xxx": {"status":"REQUIRES_CONFIRMATION","memberId":"...","clmUid":"...","amount":"...", "currency":"USD"}
}

# ===== Accumulators (by coverageKey) =====
ACCUMULATORS_DB: Dict[str, List[AccumulatorEntry]] = {
    # JOHN 2025 PPO
    "1J1U-20250101-20251231-MED-57AMFC": [
        AccumulatorEntry(
            category="DED",
            scope="INDV",
            tier="INN",
            accumulated="250.00",
            maximum="1000.00",
        ),
        AccumulatorEntry(
            category="OOP",
            scope="INDV",
            tier="INN",
            accumulated="400.00",
            maximum="3000.00",
        ),
        AccumulatorEntry(
            category="DED",
            scope="FAM",
            tier="INN",
            accumulated="700.00",
            maximum="3000.00",
        ),
        AccumulatorEntry(
            category="OOP",
            scope="FAM",
            tier="INN",
            accumulated="1200.00",
            maximum="6000.00",
        ),
        # OON examples
        AccumulatorEntry(
            category="DED",
            scope="INDV",
            tier="OON",
            accumulated="0.00",
            maximum="3000.00",
        ),
        AccumulatorEntry(
            category="OOP",
            scope="INDV",
            tier="OON",
            accumulated="0.00",
            maximum="9000.00",
        ),
    ],
    # JANE 2025 HMO (no deductible; OOP tracking)
    "9Z9X-20250101-20251231-MED-INDHMO": [
        AccumulatorEntry(
            category="DED", scope="INDV", tier="INN", accumulated="0.00", maximum="0.00"
        ),
        AccumulatorEntry(
            category="OOP",
            scope="INDV",
            tier="INN",
            accumulated="1200.00",
            maximum="4500.00",
        ),
    ],
}

# ===== Member preferences (by mbrUid) =====
MEMBER_PREFERENCES: Dict[str, MemberPreferences] = {
    "121231234": MemberPreferences(
        language="en-us", emailOptIn=True, smsOptIn=False, accessibility="True"
    ),  # JOHN
    "882771300": MemberPreferences(
        language="en-us", emailOptIn=False, smsOptIn=True, accessibility="large_text"
    ),  # JANE
    "121231235": MemberPreferences(
        language="en-us", emailOptIn=False, smsOptIn=False, accessibility=None
    ),  # SARA
    "121231236": MemberPreferences(
        language="en-us", emailOptIn=False, smsOptIn=False, accessibility=None
    ),  # TOM
}

# Default home location per member (stateCode + zipCode).
# Used by find_care_* endpoints as a fallback when no location is supplied in the request body.
MEMBER_DEFAULT_LOCATIONS: Dict[str, Dict[str, str]] = {
    "121231234": {"stateCode": "NY", "zipCode": "11211"},  # JOHN DOE
    "121231235": {"stateCode": "NY", "zipCode": "11211"},  # SARA DOE (same household)
    "121231236": {"stateCode": "NY", "zipCode": "11211"},  # TOM DOE (same household)
    "121231233": {"stateCode": "NY", "zipCode": "11211"},  # JENNY DOE (spouse)
    "882771300": {"stateCode": "MA", "zipCode": "02108"},  # JANE SMITH (Boston)
    "868Y10397": {"stateCode": "NY", "zipCode": "11211"},  # JOHN by accountId
}

# Global DBs (exports)
# =====================================================

CLAIMS_DB: List[ServiceRecord] = seed_claims()
CLAIM_DETAILS_DB = build_claim_details_index(CLAIMS_DB)
ELIGIBILITY_DB, COVERAGE_KEY_INDEX, PLAN_INFO_DB, CONTRACT_UID_TO_CD = (
    seed_eligibility_and_plans()
)

# =====================================================
# Plans Catalog
# =====================================================


def _cs(
    ind_ded: str,
    fam_ded: str,
    ind_oop: str,
    fam_oop: str,
    pcp: str,
    spec: str,
    prev: str,
    urg: str,
    er: str,
    inp: str,
    ops: str,
    lab: str,
    img: str,
    mh_inp: str,
    mh_out: str,
) -> CostStructure:
    return CostStructure(
        individualDeductible=ind_ded,
        familyDeductible=fam_ded,
        individualOopMax=ind_oop,
        familyOopMax=fam_oop,
        primaryCareCopay=pcp,
        specialistCopay=spec,
        preventiveCare=prev,
        urgentCareCopay=urg,
        erCopay=er,
        inpatientHospital=inp,
        outpatientSurgery=ops,
        labWork=lab,
        imaging=img,
        mentalHealthInpatient=mh_inp,
        mentalHealthOutpatient=mh_out,
    )


def _dt(t1: str, t2: str, t3: str, t4: str, mail: str) -> DrugTiers:
    return DrugTiers(
        tier1Generic=t1,
        tier2PreferredBrand=t2,
        tier3NonPreferredBrand=t3,
        tier4Specialty=t4,
        mailOrder90Day=mail,
    )


PLAN_CATALOG: Dict[str, PlanDetail] = {
    # ------------------------------------------------------------------
    # PPO PREMIER — highest premium, broadest coverage, OON safety net
    # ------------------------------------------------------------------
    "OAK-PPO-PREMIER-2025": PlanDetail(
        planId="OAK-PPO-PREMIER-2025",
        planName="Oak Premier PPO",
        planType="PPO",
        marketSegment="Group",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$650", family="$1,850"),
        network=PlanNetworkInfo(
            networkName="Oak Premier Network", networkCode="PREMIER-NET", tier="Premier"
        ),
        features=PlanFeatures(
            referralRequired=False,
            outOfNetworkCoverage=True,
            hsaEligible=False,
            fsaEligible=True,
            pcpRequired=False,
            telehealthIncluded=True,
        ),
        planContractCode="CONTRACT-PPO-PREMIER-2025",
        networkBrandCode="ACME",
        highlights=[
            "No referrals required",
            "$0 telehealth visits",
            "Out-of-network coverage at 50% coinsurance",
            "Lowest individual deductible ($500)",
            "Lowest OOP max ($4,000 individual)",
        ],
        deductibleType="embedded",
        innCoverage=_cs(
            ind_ded="$500",
            fam_ded="$1,000",
            ind_oop="$4,000",
            fam_oop="$8,000",
            pcp="$25 copay",
            spec="$50 copay",
            prev="$0 (ACA preventive)",
            urg="$50 copay",
            er="$350 copay (waived if admitted)",
            inp="20% after deductible",
            ops="20% after deductible",
            lab="$0 copay",
            img="20% after deductible",
            mh_inp="20% after deductible (parity)",
            mh_out="$25 copay",
        ),
        oonCoverage=_cs(
            ind_ded="$1,500",
            fam_ded="$3,000",
            ind_oop="$8,000",
            fam_oop="$16,000",
            pcp="50% after OON deductible",
            spec="50% after OON deductible",
            prev="50% after OON deductible",
            urg="50% after OON deductible",
            er="Covered at INN level",
            inp="50% after OON deductible",
            ops="50% after OON deductible",
            lab="50% after OON deductible",
            img="50% after OON deductible",
            mh_inp="50% after OON deductible (parity)",
            mh_out="50% after OON deductible",
        ),
        drugCoverage=_dt("$10", "$35", "$70", "20% coinsurance", "2.5x 30-day copay"),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$0",
            maternityProgram=True,
            pediatricDental=True,
            pediatricVision=True,
            chronicCareManagement=True,
            wellnessRewards=True,
        ),
        bestFor=[
            "High utilizers needing frequent specialist visits",
            "Members who travel or need out-of-network flexibility",
            "Families with predictable high medical expenses",
        ],
    ),
    # ------------------------------------------------------------------
    # PPO STANDARD — mid-tier PPO, moderate cost, OON coverage
    # ------------------------------------------------------------------
    "OAK-PPO-STANDARD-2025": PlanDetail(
        planId="OAK-PPO-STANDARD-2025",
        planName="Oak Standard PPO",
        planType="PPO",
        marketSegment="Group",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$450", family="$1,300"),
        network=PlanNetworkInfo(
            networkName="Oak Standard Network",
            networkCode="STANDARD-NET",
            tier="Standard",
        ),
        features=PlanFeatures(
            referralRequired=False,
            outOfNetworkCoverage=True,
            hsaEligible=False,
            fsaEligible=True,
            pcpRequired=False,
            telehealthIncluded=True,
        ),
        planContractCode="CONTRACT-PPO-STANDARD-2025",
        networkBrandCode="ACME",
        highlights=[
            "No referrals required",
            "Out-of-network coverage at 40% coinsurance",
            "Moderate premium with PPO flexibility",
        ],
        deductibleType="embedded",
        innCoverage=_cs(
            ind_ded="$1,500",
            fam_ded="$3,000",
            ind_oop="$7,000",
            fam_oop="$14,000",
            pcp="$30 copay",
            spec="$60 copay",
            prev="$0 (ACA preventive)",
            urg="$75 copay",
            er="$400 copay (waived if admitted)",
            inp="20% after deductible",
            ops="20% after deductible",
            lab="$15 copay",
            img="20% after deductible",
            mh_inp="20% after deductible (parity)",
            mh_out="$30 copay",
        ),
        oonCoverage=_cs(
            ind_ded="$3,000",
            fam_ded="$6,000",
            ind_oop="$14,000",
            fam_oop="$28,000",
            pcp="40% after OON deductible",
            spec="40% after OON deductible",
            prev="40% after OON deductible",
            urg="40% after OON deductible",
            er="Covered at INN level",
            inp="40% after OON deductible",
            ops="40% after OON deductible",
            lab="40% after OON deductible",
            img="40% after OON deductible",
            mh_inp="40% after OON deductible (parity)",
            mh_out="40% after OON deductible",
        ),
        drugCoverage=_dt("$15", "$45", "$85", "25% coinsurance", "2.5x 30-day copay"),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$15",
            maternityProgram=True,
            pediatricDental=False,
            pediatricVision=False,
            chronicCareManagement=True,
            wellnessRewards=False,
        ),
        bestFor=[
            "Members who want PPO flexibility without the Premier premium",
            "Moderate utilizers who occasionally need OON care",
        ],
    ),
    # ------------------------------------------------------------------
    # HMO CLASSIC — coordinated care, lower premium, NO OON
    # ------------------------------------------------------------------
    "OAK-HMO-CLASSIC-2025": PlanDetail(
        planId="OAK-HMO-CLASSIC-2025",
        planName="Oak Classic HMO",
        planType="HMO",
        marketSegment="Group",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$350", family="$1,000"),
        network=PlanNetworkInfo(
            networkName="Oak Classic HMO Network",
            networkCode="HMO-CLASSIC-NET",
            tier="Standard",
        ),
        features=PlanFeatures(
            referralRequired=True,
            outOfNetworkCoverage=False,
            hsaEligible=False,
            fsaEligible=True,
            pcpRequired=True,
            telehealthIncluded=True,
        ),
        planContractCode="CONTRACT-HMO-CLASSIC-2025",
        networkBrandCode="ACME",
        highlights=[
            "Lower premium than PPO options",
            "$0 telehealth visits",
            "PCP-coordinated care model",
            "Referrals required for specialist visits",
            "No out-of-network coverage (emergency only)",
        ],
        deductibleType="embedded",
        innCoverage=_cs(
            ind_ded="$750",
            fam_ded="$1,500",
            ind_oop="$5,000",
            fam_oop="$10,000",
            pcp="$20 copay",
            spec="$45 copay (referral required)",
            prev="$0 (ACA preventive)",
            urg="$50 copay",
            er="$300 copay (waived if admitted)",
            inp="$300 per admission",
            ops="20% after deductible",
            lab="$0 copay",
            img="20% after deductible",
            mh_inp="$300 per admission (parity)",
            mh_out="$25 copay",
        ),
        oonCoverage=None,  # No OON coverage; emergency only
        drugCoverage=_dt("$10", "$30", "$60", "20% coinsurance", "2.5x 30-day copay"),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$0",
            maternityProgram=True,
            pediatricDental=True,
            pediatricVision=True,
            chronicCareManagement=True,
            wellnessRewards=False,
        ),
        bestFor=[
            "Cost-conscious members who prefer coordinated care",
            "Members who stay in-network and rarely travel",
            "Those who want a primary doctor managing all referrals",
        ],
    ),
    # ------------------------------------------------------------------
    # HDHP + HSA — lowest premium, high deductible, HSA-eligible
    # TRAP: aggregate deductible — entire family pool must be met
    # ------------------------------------------------------------------
    "OAK-HDHP-2025": PlanDetail(
        planId="OAK-HDHP-2025",
        planName="Oak HDHP + HSA",
        planType="HDHP",
        marketSegment="Individual",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$280", family="$820"),
        network=PlanNetworkInfo(
            networkName="Oak HDHP Network", networkCode="HDHP-NET", tier="Standard"
        ),
        features=PlanFeatures(
            referralRequired=False,
            outOfNetworkCoverage=True,
            hsaEligible=True,
            fsaEligible=False,
            pcpRequired=False,
            telehealthIncluded=True,
        ),
        planContractCode="CONTRACT-HDHP-2025",
        networkBrandCode="ACME",
        highlights=[
            "Lowest monthly premium ($280 individual)",
            "HSA-eligible — 2025 limit: $4,300 individual / $8,550 family (pre-tax savings)",
            "AGGREGATE family deductible — full $3,200 must be met collectively before coverage kicks in",
            "All services subject to deductible EXCEPT preventive care and telehealth",
            "Out-of-network coverage at 40% coinsurance",
        ],
        deductibleType="aggregate",
        innCoverage=_cs(
            ind_ded="$1,600",
            fam_ded="$3,200 (aggregate — no embedded individual limit)",
            ind_oop="$5,000",
            fam_oop="$10,000",
            pcp="20% after deductible (no copay before deductible met)",
            spec="20% after deductible (no copay before deductible met)",
            prev="$0 (ACA preventive — deductible does NOT apply)",
            urg="20% after deductible",
            er="20% after deductible",
            inp="20% after deductible",
            ops="20% after deductible",
            lab="20% after deductible",
            img="20% after deductible",
            mh_inp="20% after deductible (parity)",
            mh_out="20% after deductible",
        ),
        oonCoverage=_cs(
            ind_ded="$3,200",
            fam_ded="$6,400 (aggregate)",
            ind_oop="$10,000",
            fam_oop="$20,000",
            pcp="40% after OON deductible",
            spec="40% after OON deductible",
            prev="$0 (ACA preventive)",
            urg="40% after OON deductible",
            er="20% after INN deductible",
            inp="40% after OON deductible",
            ops="40% after OON deductible",
            lab="40% after OON deductible",
            img="40% after OON deductible",
            mh_inp="40% after OON deductible (parity)",
            mh_out="40% after OON deductible",
        ),
        drugCoverage=_dt(
            "20% after deductible",
            "20% after deductible",
            "30% after deductible",
            "30% after deductible",
            "2.5x 30-day cost",
        ),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$0 (pre-deductible eligible)",
            maternityProgram=True,
            pediatricDental=False,
            pediatricVision=False,
            chronicCareManagement=False,
            wellnessRewards=False,
        ),
        bestFor=[
            "Healthy individuals who rarely use healthcare",
            "Members who want to maximize tax-advantaged HSA savings",
            "Single members — aggregate deductible is less of a trap for individuals",
        ],
    ),
    # ------------------------------------------------------------------
    # EPO SELECT — no referrals, no OON, mid-tier price
    # ------------------------------------------------------------------
    "OAK-EPO-SELECT-2025": PlanDetail(
        planId="OAK-EPO-SELECT-2025",
        planName="Oak Select EPO",
        planType="EPO",
        marketSegment="Individual",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$400", family="$1,150"),
        network=PlanNetworkInfo(
            networkName="Oak Select EPO Network",
            networkCode="SELECT-NET",
            tier="Standard",
        ),
        features=PlanFeatures(
            referralRequired=False,
            outOfNetworkCoverage=False,
            hsaEligible=False,
            fsaEligible=True,
            pcpRequired=False,
            telehealthIncluded=True,
        ),
        planContractCode="CONTRACT-EPO-SELECT-2025",
        networkBrandCode="ACME",
        highlights=[
            "No referrals required — see specialists directly",
            "$0 telehealth visits",
            "No out-of-network coverage (emergency only) — lower premium vs PPO",
            "Good balance of cost and flexibility for in-network users",
        ],
        deductibleType="embedded",
        innCoverage=_cs(
            ind_ded="$1,000",
            fam_ded="$2,000",
            ind_oop="$6,000",
            fam_oop="$12,000",
            pcp="$25 copay",
            spec="$55 copay (no referral needed)",
            prev="$0 (ACA preventive)",
            urg="$60 copay",
            er="$350 copay (waived if admitted)",
            inp="20% after deductible",
            ops="20% after deductible",
            lab="$0 copay",
            img="20% after deductible",
            mh_inp="20% after deductible (parity)",
            mh_out="$25 copay",
        ),
        oonCoverage=None,  # No OON coverage; emergency only
        drugCoverage=_dt("$12", "$40", "$75", "22% coinsurance", "2.5x 30-day copay"),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$0",
            maternityProgram=True,
            pediatricDental=True,
            pediatricVision=True,
            chronicCareManagement=True,
            wellnessRewards=False,
        ),
        bestFor=[
            "Members who want HMO-level premiums without referral requirements",
            "Those who stay in-network and value specialist access",
            "Individuals who travel rarely and can accept zero OON coverage",
        ],
    ),
    # ------------------------------------------------------------------
    # POS FLEX — referrals INN, self-refer OON, hybrid model
    # ------------------------------------------------------------------
    "OAK-POS-FLEX-2025": PlanDetail(
        planId="OAK-POS-FLEX-2025",
        planName="Oak Flex POS",
        planType="POS",
        marketSegment="Group",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$500", family="$1,450"),
        network=PlanNetworkInfo(
            networkName="Oak Flex POS Network",
            networkCode="POS-FLEX-NET",
            tier="Standard",
        ),
        features=PlanFeatures(
            referralRequired=True,
            outOfNetworkCoverage=True,
            hsaEligible=False,
            fsaEligible=True,
            pcpRequired=True,
            telehealthIncluded=True,
        ),
        planContractCode="CONTRACT-POS-FLEX-2025",
        networkBrandCode="ACME",
        highlights=[
            "Out-of-network coverage without a referral (self-refer OON at 30% coinsurance)",
            "Referrals required for in-network specialists only",
            "Lower INN deductible ($500) with OON safety net",
            "Telehealth at $5 copay",
        ],
        deductibleType="embedded",
        innCoverage=_cs(
            ind_ded="$500",
            fam_ded="$1,000",
            ind_oop="$5,500",
            fam_oop="$11,000",
            pcp="$25 copay",
            spec="$50 copay (referral required INN)",
            prev="$0 (ACA preventive)",
            urg="$60 copay",
            er="$350 copay (waived if admitted)",
            inp="20% after deductible",
            ops="20% after deductible",
            lab="$0 copay",
            img="20% after deductible",
            mh_inp="20% after deductible (parity)",
            mh_out="$25 copay",
        ),
        oonCoverage=_cs(
            ind_ded="$1,500",
            fam_ded="$3,000",
            ind_oop="$11,000",
            fam_oop="$22,000",
            pcp="30% after OON deductible (self-refer, no referral needed OON)",
            spec="30% after OON deductible (self-refer)",
            prev="30% after OON deductible",
            urg="30% after OON deductible",
            er="Covered at INN level",
            inp="30% after OON deductible",
            ops="30% after OON deductible",
            lab="30% after OON deductible",
            img="30% after OON deductible",
            mh_inp="30% after OON deductible (parity)",
            mh_out="30% after OON deductible",
        ),
        drugCoverage=_dt("$10", "$40", "$80", "25% coinsurance", "2.5x 30-day copay"),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$5",
            maternityProgram=True,
            pediatricDental=False,
            pediatricVision=False,
            chronicCareManagement=True,
            wellnessRewards=True,
        ),
        bestFor=[
            "Members who prefer a PCP but want OON flexibility without a referral",
            "Those who occasionally need to self-refer out-of-network",
            "Families needing both coordination and flexibility",
        ],
    ),
    # ------------------------------------------------------------------
    # HMO VALUE — cheapest option, highest OOP max, limited network
    # TRAP: aggregate deductible + statutory OOP max ($8,700)
    # ------------------------------------------------------------------
    "OAK-HMO-VALUE-2025": PlanDetail(
        planId="OAK-HMO-VALUE-2025",
        planName="Oak Value HMO",
        planType="HMO",
        marketSegment="Individual",
        stateCode="NY",
        effectiveDate="2025-01-01",
        terminationDate="2025-12-31",
        estimatedMonthlyPremium=PlanPremium(individual="$200", family="$580"),
        network=PlanNetworkInfo(
            networkName="Oak Value HMO Network", networkCode="VALUE-NET", tier="Value"
        ),
        features=PlanFeatures(
            referralRequired=True,
            outOfNetworkCoverage=False,
            hsaEligible=False,
            fsaEligible=True,
            pcpRequired=True,
            telehealthIncluded=False,
        ),
        planContractCode="CONTRACT-HMO-VALUE-2025",
        networkBrandCode="ACME",
        highlights=[
            "Lowest monthly premium ($200 individual)",
            "AGGREGATE family deductible ($4,000) — all family members pool toward one total",
            "Highest OOP max ($8,700 individual — ACA statutory maximum)",
            "Limited provider network (Value tier — fewer choices)",
            "Referrals required; telehealth has a $10 copay",
            "No out-of-network coverage (emergency only)",
        ],
        deductibleType="aggregate",
        innCoverage=_cs(
            ind_ded="$2,000",
            fam_ded="$4,000 (aggregate — no embedded individual limit)",
            ind_oop="$8,700 (ACA statutory maximum)",
            fam_oop="$17,400",
            pcp="$35 copay",
            spec="$65 copay (referral required)",
            prev="$0 (ACA preventive)",
            urg="$75 copay",
            er="$500 copay (waived if admitted)",
            inp="$500 per admission",
            ops="30% after deductible",
            lab="$15 copay",
            img="30% after deductible",
            mh_inp="$500 per admission (parity)",
            mh_out="$35 copay",
        ),
        oonCoverage=None,  # No OON coverage; emergency only
        drugCoverage=_dt("$15", "$50", "$100", "30% coinsurance", "2.5x 30-day copay"),
        specialBenefits=SpecialBenefits(
            telehealthCopay="$10",
            maternityProgram=False,
            pediatricDental=False,
            pediatricVision=False,
            chronicCareManagement=False,
            wellnessRewards=False,
        ),
        bestFor=[
            "Very healthy individuals who want the lowest possible monthly cost",
            "Members with limited budget who rarely use healthcare",
        ],
    ),
}

__all__ = [
    "CLAIMS_DB",
    "CLAIM_DETAILS_DB",
    "ELIGIBILITY_DB",
    "COVERAGE_KEY_INDEX",
    "PLAN_INFO_DB",
    "STATUS_CODEBOOK",
    "CONTRACT_UID_TO_CD",
    "SUPPORTED_BENEFIT_INTENTS",
    "BENEFIT_DETAILS_DB",
    "PROVIDERS_DB",
    "SUGGESTIONS_DB",
    "MEDICAL_KB",
    "BILLING_LEDGER",
    "PAYMENT_INTENTS",
    "ACCUMULATORS_DB",
    "MEMBER_PREFERENCES",
    "MEMBER_DEFAULT_LOCATIONS",
    "PLAN_CATALOG",
]

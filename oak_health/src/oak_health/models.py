from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

# ===== Request Models =====


class GetMemberClaimsRequest(BaseModel):
    memberId: str = Field(..., description="Member ID to fetch claims for")


# ===== Core Shared Models =====


class MetadataTriple(BaseModel):
    identifier: str
    label: str
    details: str


class PersonIdentity(BaseModel):
    """Identity information separated from personal data"""

    primaryId: str
    secondaryId: str


class PersonRecord(BaseModel):
    identity: PersonIdentity
    givenName: str
    familyName: str
    birthDate: str


class CostAllocation(BaseModel):
    """Part of FinancialBreakdown - cost allocation details"""

    approved: Optional[str] = None
    patientShare: Optional[str] = None
    providerShare: Optional[str] = None
    excluded: Optional[str] = None


class CostSharing(BaseModel):
    """Part of FinancialBreakdown - cost sharing details"""

    coinsurance: Optional[str] = None
    fixedFee: Optional[str] = None
    deductible: Optional[str] = None


class PaymentSummary(BaseModel):
    """Part of FinancialBreakdown - payment summary"""

    disbursed: Optional[str] = None
    billed: Optional[str] = None
    gross: Optional[str] = None
    service: Optional[str] = None


class PlanBenefits(BaseModel):
    """Part of FinancialBreakdown - plan benefits"""

    discount: Optional[str] = None
    savings: Optional[str] = None


class FinancialBreakdown(BaseModel):
    allocation: CostAllocation
    sharing: CostSharing
    payment: PaymentSummary
    benefits: PlanBenefits


class ServiceEntity(BaseModel):
    entityName: Optional[str] = None
    taxIdentifier: Optional[str] = None
    entityType: str = "PROVIDER"


# ===== Claims Models =====


class MedicalCode(BaseModel):
    """Medical procedure or diagnosis code"""

    code: str


class DiagnosisSet(BaseModel):
    """Set of diagnosis codes"""

    codes: List[MedicalCode]


class LineItemPeriod(BaseModel):
    """Service line item time period"""

    start: str
    end: str


class LineItemFinancials(BaseModel):
    """Service line item financial details"""

    approved: Optional[str] = None
    deductible: Optional[str] = None
    coinsurance: Optional[str] = None
    fixedFee: Optional[str] = None
    patientOwes: Optional[str] = None
    notCovered: Optional[str] = None
    planSavings: Optional[str] = None
    planDiscount: Optional[str] = None
    charged: Optional[str] = None
    paid: Optional[str] = None


class ServiceLineItem(BaseModel):
    period: LineItemPeriod
    financials: LineItemFinancials
    procedure: MedicalCode
    diagnosisSets: List[DiagnosisSet]


class ExplanationIdentifiers(BaseModel):
    """EOB identification information"""

    uniqueId: str
    sourceSystem: str
    memberId: str
    sequenceNumber: str
    legacyReference: Optional[str] = None


class PaymentDetails(BaseModel):
    """Payment information for EOB"""

    checkNumber: Optional[str] = None
    checkDate: Optional[str] = None


class ExplanationRecord(BaseModel):
    identifiers: ExplanationIdentifiers
    date: str
    payment: PaymentDetails
    relatedRecordId: str
    serviceStart: str
    serviceEnd: str
    processedDate: str
    subscriberName: str
    patientName: str
    jurisdiction: Optional[str] = None


class RecordIdentifiers(BaseModel):
    """Claim record identifiers"""

    uniqueId: str
    displayId: str
    referenceId: str


class RecordFlags(BaseModel):
    """Claim record flags - converted Y/N to boolean"""

    accountType: bool
    paymentEnabled: bool
    confidential: bool
    prepaidService: bool
    minorProtected: Optional[bool] = None


class RecordClassification(BaseModel):
    """Claim record classification"""

    source: MetadataTriple
    category: MetadataTriple
    type: MetadataTriple
    status: MetadataTriple


class ServiceTimeline(BaseModel):
    """Service timeline dates"""

    serviceStart: str
    serviceEnd: str
    received: str
    processed: str


class ServiceParties(BaseModel):
    """Parties involved in service"""

    subject: PersonRecord
    servicingEntity: ServiceEntity
    billingEntity: ServiceEntity


class ServiceRecord(BaseModel):
    identifiers: RecordIdentifiers
    flags: RecordFlags
    classification: RecordClassification
    timeline: ServiceTimeline
    parties: ServiceParties
    financial: FinancialBreakdown
    networkIdentifier: Optional[str] = None
    lineItems: Optional[List[ServiceLineItem]] = None
    explanations: Optional[List[ExplanationRecord]] = None


# ===== Response Models for claims =====


class PageInfo(BaseModel):
    size: int
    totalElements: int
    totalPages: int
    number: int


class ClaimsResponse(BaseModel):
    metadata: dict
    claims: List[ServiceRecord]


# ===== Coverage Models =====


class Vendor(BaseModel):
    vendorNm: str


class ProductType(BaseModel):
    coverageTypeCd: MetadataTriple
    vendor: List[Vendor]


class RelationshipCd(BaseModel):
    code: str
    name: str
    description: str


class GenderCd(BaseModel):
    code: str
    name: str
    description: str


class PersonName(BaseModel):
    """Separated name components"""

    given: str
    middle: Optional[str] = None
    family: str


class EnrollmentDates(BaseModel):
    """Enrollment date range"""

    effective: str
    termination: Optional[str] = None


class EnrolledPerson(BaseModel):
    personId: str
    name: PersonName
    birthDate: str
    relationship: MetadataTriple
    enrollment: EnrollmentDates
    status: MetadataTriple
    productTypes: List[MetadataTriple]
    sequenceNumber: str
    primaryAccountId: str
    gender: MetadataTriple


class PeriodDates(BaseModel):
    """Coverage period dates"""

    start: str
    end: Optional[str] = None


class PeriodFeatures(BaseModel):
    """Coverage period features - converted indicators to booleans"""

    salaryBasedLimit: bool
    enhancedProgram: bool
    dependentEligible: bool


class EnrollmentPeriod(BaseModel):
    periodKey: str
    dates: PeriodDates
    features: PeriodFeatures
    enrollmentType: MetadataTriple
    status: MetadataTriple
    productTypes: List[ProductType]
    productName: str
    systemReference: str
    enrollees: List[EnrolledPerson]
    benefitCycle: str
    arrangement: MetadataTriple


class ContractIdentifiers(BaseModel):
    """Contract identification information"""

    accountId: str
    contractNumber: str
    contractUniqueId: str


class GroupInfo(BaseModel):
    """Group information"""

    groupId: str
    groupName: str


class ContractRecord(BaseModel):
    identifiers: ContractIdentifiers
    group: GroupInfo
    effectiveDate: str
    status: MetadataTriple
    brand: MetadataTriple
    sourceSystem: str
    periods: List[EnrollmentPeriod]


class CoveragePeriodResponse(BaseModel):
    eligibility: List[ContractRecord]


# ===== Plan Information Models =====


class BenefitPeriod(BaseModel):
    cd: str
    desc: str


class BenefitItem(BaseModel):
    cd: str
    value: str
    unit: Optional[str] = None
    desc: str
    optionNm: Optional[str] = None
    optionDesc: Optional[str] = None


class CostShareEntry(BaseModel):
    benefit: BenefitItem
    coverageLevel: Optional[str] = None
    coverageCd: Optional[str] = None
    timePeriod: Optional[str] = None


class NetworkPlan(BaseModel):
    cd: str
    desc: str
    costShare: List[CostShareEntry]


class ValueBasedProviderInfo(BaseModel):
    coverageFlag: str


class PlanInformationResponse(BaseModel):
    contractCd: str
    contractState: str
    startDt: str
    endDt: str
    marketSegment: str
    planType: str
    benefitPeriod: BenefitPeriod
    valueBasedProviderInfo: ValueBasedProviderInfo
    network: List[NetworkPlan]


# ===== Benefits Models =====


class CostComponent(BaseModel):
    type: str
    value: str


class NetworkCostStructure(BaseModel):
    networkCode: str
    networkLabel: str
    deductibleRequired: str
    priorAuthRequired: str
    costComponents: List[CostComponent]


class POS(BaseModel):
    posCd: Optional[str] = None
    posDesc: str


class CoverageScenario(BaseModel):
    pos: List[POS]
    networks: List[NetworkCostStructure]


class CoverageSpecification(BaseModel):
    specificationName: str
    category: str
    applicableSettings: List[str]
    systemIdentifier: str
    scenarios: List[CoverageScenario]


class ServiceEntry(BaseModel):
    categoryNm: str
    benefits: List[CoverageSpecification]


class CategoryEntry(BaseModel):
    services: List[ServiceEntry]


class ProductCategory(BaseModel):
    planType: str
    categories: List[CategoryEntry]


class RelatedProcedure(BaseModel):
    code: str
    name: str


class InquiryContext(BaseModel):
    """Context information for benefit inquiry"""

    memberId: str
    contractReference: str
    contractCode: str
    documentId: str
    effectiveDate: str
    searchQuery: str


class CoverageInquiryResult(BaseModel):
    context: InquiryContext
    categories: List[ProductCategory]
    relatedProcedures: Optional[List[RelatedProcedure]] = None


class BenefitsSearchResponse(BaseModel):
    benefitResults: List[CoverageInquiryResult]


# ===== Benefit Details Models =====


class DetailCostComponent(BaseModel):
    """Cost component for benefit details"""

    type: str
    value: str


class DetailNetworkCostStructure(BaseModel):
    """Network cost structure for benefit details"""

    code: str  # e.g., "INN", "OON"
    type: str  # e.g., "In Network", "Out of Network"
    deductibleApplies: str
    precertRequired: str
    costshares: List[DetailCostComponent]


class DetailPOS(BaseModel):
    posCd: Optional[str] = None
    posDesc: str


class DetailCoverageScenario(BaseModel):
    """Coverage scenario for benefit details"""

    pos: List[DetailPOS]
    diagnosisCd: List[str]
    networks: List[DetailNetworkCostStructure]


class ServiceBenefitDetail(BaseModel):
    benefitNm: str
    benefitType: str
    specialtyType: List[str]
    srvcDefnId: List[str]
    situations: List[DetailCoverageScenario]


class ServiceDetailsGroup(BaseModel):
    categoryNm: str
    service: List[ServiceBenefitDetail]


class ServiceCategoryDetails(BaseModel):
    planType: str
    services: List[ServiceDetailsGroup]


class PlanLevelBenefitsGroup(BaseModel):
    networks: List[DetailNetworkCostStructure]


class PlanLevelEntry(BaseModel):
    planType: str
    benefits: List[PlanLevelBenefitsGroup]


class BenefitDetailsResult(BaseModel):
    mcid: str
    contractUID: str
    effectiveDt: str
    benefitSysId: str
    serviceCategory: List[ServiceCategoryDetails]
    planLevel: List[PlanLevelEntry]


class BenefitsDetailsResponse(BaseModel):
    benefitResults: List[BenefitDetailsResult]


# ===== Provider/Care Models =====


class AddressComponents(BaseModel):
    """Separated address components"""

    line1: str
    line2: Optional[str] = None
    city: str
    stateCode: str
    zipCode: str
    county: Optional[str] = None
    country: str


class ContactInfo(BaseModel):
    """Contact information"""

    phone: Optional[str] = None
    email: Optional[str] = None


class GeoCoordinates(BaseModel):
    """Holds the calculated distance to a provider. Requests use stateCode + zipCode in LocationContext"""

    distanceMiles: float


class LocationDetails(BaseModel):
    facilityName: str
    locationId: str
    address: AddressComponents
    contact: ContactInfo
    coordinates: GeoCoordinates


class ProviderTaxonomy(BaseModel):
    code: str
    name: str
    description: str


class ExpertiseProfile(BaseModel):
    taxonomies: List[ProviderTaxonomy]
    specialtyCategories: List[str]  # e.g., ["25", "231", "75"]


class NetworkParticipation(BaseModel):
    status: str  # e.g., "TP_INNETWORK"
    accept_new_patients: bool
    coverages: List[str]  # e.g., ["MED"]


class CareProviderProfile(BaseModel):
    providerId: str
    name: str
    address: LocationDetails
    expertise: ExpertiseProfile
    network: NetworkParticipation


class FindCareSpecialtyResponse(BaseModel):
    providers: List[CareProviderProfile]


# ===== Find Care Suggestions Models =====


class SuggestionCriteria(BaseModel):
    taxonomyList: List[ProviderTaxonomy]
    specialtyCategoryList: List[MetadataTriple]
    genderList: List[str] = []
    languageList: List[MetadataTriple] = []
    providerName: Optional[str] = ""
    ableToServeAsPcp: Optional[bool] = False
    acceptsNewPatient: Optional[bool] = False
    npi: Optional[str] = ""


class SuggestionItem(BaseModel):
    text: str
    type: str  # e.g., SPECIALTY, PROVIDER_NAME, PROCEDURE
    score: float
    criteria: SuggestionCriteria
    procedureCode: Optional[str] = None
    medicalCode: Optional[str] = None
    metaData: Dict[str, Any] = {}
    dplQueryParams: Dict[str, str] = {}


class SuggestionLocationDetails(BaseModel):
    """Location details for suggestions"""

    city: Optional[str] = ""
    countyCode: Optional[str] = ""
    countyName: Optional[str] = ""
    displayName: Optional[str] = ""
    distance: Optional[str] = ""
    fipsStCd: Optional[str] = ""
    locationType: Optional[str] = "ZIP_CODE"
    stateCode: Optional[str] = ""
    stateName: Optional[str] = ""
    zipCode: Optional[str] = ""


class FindCareSuggestionsResponse(BaseModel):
    primarySearchIntent: str
    suggestionList: List[SuggestionItem]
    locationDetails: SuggestionLocationDetails


# ===== Medical Information Models =====


class ConsumerText(BaseModel):
    consumer: Dict[str, str]


class MedicalArticle(BaseModel):
    id: str
    type: str = "article"
    title: ConsumerText
    abstract: ConsumerText
    url: str


class MedicalInformationResponse(BaseModel):
    status: str
    items: List[MedicalArticle]


# ===== Billing Models =====


class BillingItem(BaseModel):
    identifiers: Dict[str, str]  # uniqueId, displayId
    amountDue: str
    dueDate: Optional[str] = None
    paymentStatus: str
    onlinePaymentEnabled: bool


class BillingResponse(BaseModel):
    items: List[BillingItem]
    totals: Dict[str, str]


# ===== EOB PDF Models =====


class EobPdfItem(BaseModel):
    documentId: str
    documentUrl: str
    contentType: str
    fileSize: int


class EobPdfResponse(BaseModel):
    identifiers: Dict[str, str]  # uniqueId
    explanations: List[EobPdfItem]


# ===== Payment Models =====


class CreatePaymentIntentResponse(BaseModel):
    transactionId: str
    state: str
    authToken: str
    totalAmount: str
    currencyCode: str = "USD"
    linkedClaim: Optional[str] = None


class ConfirmPaymentIntentResponse(BaseModel):
    transactionId: str
    state: str
    receiptUrl: str
    totalAmount: str
    currencyCode: str = "USD"
    linkedClaim: Optional[str] = None


# ===== Benefit Accumulators Models =====


class AccumulatorEntry(BaseModel):
    category: str
    scope: str
    tier: str
    accumulated: str
    maximum: str


class BenefitAccumulatorsResponse(BaseModel):
    planYear: str
    periodId: str
    tracking: List[AccumulatorEntry]


# ===== Member Profile & Preferences Models =====


class MemberPreferences(BaseModel):
    language: str
    emailOptIn: bool
    smsOptIn: bool
    accessibility: Optional[str] = None


class MemberProfile(BaseModel):
    identity: Dict[str, str]  # primaryId, secondaryId
    identifiers: Dict[str, str]  # accountId
    givenName: str
    familyName: str
    birthDate: str
    relationship: Dict[str, str]  # identifier, label, details


class MemberProfileResponse(BaseModel):
    member: MemberProfile
    preferences: MemberPreferences
    pcpProviderId: Optional[str] = None


class SetMemberPreferencesRequest(GetMemberClaimsRequest):
    preferences: MemberPreferences


# ===== Plans Catalog Models =====


class PlanPremium(BaseModel):
    individual: str
    family: str


class PlanNetworkInfo(BaseModel):
    networkName: str
    networkCode: str
    tier: str  # "Premier" | "Standard" | "Value"


class PlanFeatures(BaseModel):
    referralRequired: bool
    outOfNetworkCoverage: bool
    hsaEligible: bool
    fsaEligible: bool
    pcpRequired: bool
    telehealthIncluded: bool


class CostStructure(BaseModel):
    individualDeductible: str
    familyDeductible: str
    individualOopMax: str
    familyOopMax: str
    primaryCareCopay: str
    specialistCopay: str
    preventiveCare: str
    urgentCareCopay: str
    erCopay: str
    inpatientHospital: str
    outpatientSurgery: str
    labWork: str
    imaging: str
    mentalHealthInpatient: str
    mentalHealthOutpatient: str


class DrugTiers(BaseModel):
    tier1Generic: str
    tier2PreferredBrand: str
    tier3NonPreferredBrand: str
    tier4Specialty: str
    mailOrder90Day: str


class SpecialBenefits(BaseModel):
    telehealthCopay: str
    maternityProgram: bool
    pediatricDental: bool
    pediatricVision: bool
    chronicCareManagement: bool
    wellnessRewards: bool


class PlanSummary(BaseModel):
    planId: str
    planName: str
    planType: str  # "PPO" | "HMO" | "EPO" | "HDHP" | "POS"
    marketSegment: str  # "Individual" | "Group"
    stateCode: str
    effectiveDate: str
    terminationDate: str
    estimatedMonthlyPremium: PlanPremium
    network: PlanNetworkInfo
    features: PlanFeatures
    planContractCode: str  # bridge field: use as contract_uid in search_benefits
    networkBrandCode: str  # bridge field: use as brand_code in find_care_specialty
    highlights: List[str]


class PlanDetail(PlanSummary):
    deductibleType: str  # "embedded" | "aggregate"
    innCoverage: CostStructure
    oonCoverage: Optional[CostStructure] = None  # None for HMO/EPO
    drugCoverage: DrugTiers
    specialBenefits: SpecialBenefits
    bestFor: List[str]


class PlansListResponse(BaseModel):
    plans: List[PlanSummary]
    totalCount: int


class PlanDetailResponse(BaseModel):
    plan: PlanDetail


class PlanCompareResponse(BaseModel):
    plans: List[PlanDetail]
    comparisonDimensions: List[str]

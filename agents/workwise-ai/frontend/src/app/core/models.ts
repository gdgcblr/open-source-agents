// Enums mirrored from backend

export type BusinessType =
  | 'SOLE_PROPRIETOR'
  | 'SMALL_BUSINESS'
  | 'FACTORY_WORKER_OR_SUPERVISOR'
  | 'SALARIED_EMPLOYEE'
  | 'FREELANCER'
  | 'OTHER';

export type Objective =
  | 'INCREASE_INCOME'
  | 'INCREASE_BUSINESS_PROFIT'
  | 'REDUCE_EXPENSES'
  | 'FIND_CUSTOMERS'
  | 'IMPROVE_PRODUCTIVITY'
  | 'DISCOVER_CAREER_OPPORTUNITIES'
  | 'LEARN_VALUABLE_SKILLS'
  | 'IDENTIFY_MARKET_CHANGES'
  | 'IMPROVE_OPERATIONAL_EFFICIENCY';

export type RiskTolerance = 'LOW' | 'MEDIUM' | 'HIGH';

export type DevelopmentCategory =
  | 'GOVERNMENT_POLICY'
  | 'INDUSTRY_CHANGES'
  | 'MARKET_PRICES'
  | 'BUSINESS_INVESTMENTS'
  | 'TECHNOLOGY'
  | 'SUPPLY_CHAINS'
  | 'WEATHER_AND_CLIMATE'
  | 'EMPLOYMENT'
  | 'CUSTOMER_DEMAND'
  | 'TRAINING_AND_SKILLS'
  | 'COMPETITOR_DEVELOPMENTS';

export type EvidenceState = 'UNVERIFIED' | 'PARTIALLY_VERIFIED' | 'VERIFIED' | 'DEMONSTRATION_DATA';

export type ConfidenceLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export type ScenarioType = 'LOW' | 'BASE' | 'HIGH';

export type ActionStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' | 'SKIPPED';

// Profile

export interface UserProfileRequest {
  occupation: string;
  industry: string;
  country: string;
  region?: string | null;
  city?: string | null;
  businessType: BusinessType;
  primaryObjective: Objective;
  secondaryObjectives: string[];
  budgetAmount?: number | null;
  riskTolerance: RiskTolerance;
  relevantKeywords: string[];
  preferredLanguage: string;
  preferredCategories: string[];
}

export interface UserProfileResponse extends UserProfileRequest {
  id: string;
  createdAt: string;
  updatedAt: string;
}

// Developments / feed

export interface DevelopmentResponse {
  id: string;
  title: string;
  summary: string;
  sourceName: string | null;
  sourceUrl: string | null;
  publishedAt: string | null;
  eventAt: string | null;
  country: string | null;
  region: string | null;
  industryTags: string[];
  category: DevelopmentCategory;
  evidenceState: EvidenceState;
  demoData: boolean;
}

export interface FeedItemResponse {
  developmentId: string;
  title: string;
  summary: string;
  sourceName: string | null;
  sourceUrl: string | null;
  publishedAt: string | null;
  industryTags: string[];
  category: DevelopmentCategory;
  evidenceState: EvidenceState;
  demoData: boolean;
  relevanceScore: number;
  relevanceLabel: string;
  whyItMatters: string;
  savedAnalysisId: string | null;
}

export interface FeedResponse {
  importantForYourWork: FeedItemResponse[];
  potentialOpportunities: FeedItemResponse[];
  trends: FeedItemResponse[];
  savedAnalyses: FeedItemResponse[];
}

// Analysis

export interface AnalysisResponse {
  id: string;
  profileId: string;
  developmentId: string;
  summary: string;
  confirmedFacts: string[];
  whyItMatters: string;
  historicalComparisons: string[];
  trends: string[];
  unknowns: string[];
  nextSteps: string[];
  provider: string;
  createdAt: string;
}

// Strategies

export interface StrategyResponse {
  id: string;
  analysisId: string;
  name: string;
  description: string;
  rationale: string;
  evidence: string[];
  requiredInvestment: number | null;
  requiredResources: string[];
  timeCommitment: string | null;
  benefits: string[];
  risks: string[];
  dependencies: string[];
  failureConditions: string[];
  validationSteps: string[];
  nextAction: string | null;
  confidenceLevel: ConfidenceLevel;
  confidenceJustification: string | null;
  waitAndResearch: boolean;
  selected: boolean;
}

export interface StrategyComparisonItem {
  strategyId: string;
  name: string;
  requiredInvestment: number | null;
  timeCommitment: string | null;
  requiredResources: string[];
  risks: string[];
  dependencies: string[];
  evidenceQualityLabel: string;
  reversibilityLabel: string;
  feasibilityLabel: string;
  confidenceLevel: ConfidenceLevel;
  waitAndResearch: boolean;
}

// Financial

export interface FinancialScenarioRequest {
  strategyId: string;
  quantity: number;
  unitCost: number;
  transportCost?: number | null;
  taxesDuties?: number | null;
  handlingCost?: number | null;
  qualityControlCost?: number | null;
  otherAcquisitionCost?: number | null;
  sellingPrice: number;
  variableSellingCostPerUnit?: number | null;
  otherOperatingCost?: number | null;
  expectedSalesQuantity: number;
  unsoldInventoryAssumption?: number | null;
}

export interface FinancialScenarioResponse {
  id: string;
  strategyId: string;
  scenarioType: ScenarioType;
  quantity: number;
  unitCost: number;
  sellingPrice: number;
  expectedSalesQuantity: number;
  totalAcquisitionCost: number;
  revenue: number;
  grossMargin: number;
  contribution: number;
  netProfit: number;
  cashRequired: number;
  unsoldInventoryValue: number;
  assumptions: string[];
}

// Action plan

export interface ActionItemRequest {
  action: string;
  estimatedDuration?: string | null;
  requiredResources?: string[];
  expectedCost?: number | null;
  successMetric?: string | null;
  mainRisk?: string | null;
}

export interface ActionPlanRequest {
  strategyId: string;
  title: string;
  items: ActionItemRequest[];
}

export interface ActionItemResponse {
  id: string;
  sequenceNo: number;
  action: string;
  estimatedDuration: string | null;
  requiredResources: string[];
  expectedCost: number | null;
  successMetric: string | null;
  mainRisk: string | null;
  status: ActionStatus;
}

export interface ActionPlanResponse {
  id: string;
  strategyId: string;
  title: string;
  items: ActionItemResponse[];
}

// Outcomes

export interface StrategyOutcomeRequest {
  strategyId: string;
  dateStarted?: string | null;
  dateCompleted?: string | null;
  actualExpenses?: number | null;
  actualRevenue?: number | null;
  timeSpentHours?: number | null;
  ordersReceived?: number | null;
  customersAcquired?: number | null;
  userReportedOutcome?: string | null;
  lessonsLearned?: string | null;
}

export interface StrategyOutcomeResponse {
  id: string;
  strategyId: string;
  dateStarted: string | null;
  dateCompleted: string | null;
  actualExpenses: number | null;
  actualRevenue: number | null;
  timeSpentHours: number | null;
  ordersReceived: number | null;
  customersAcquired: number | null;
  userReportedOutcome: string | null;
  lessonsLearned: string | null;
  independentlyVerified: boolean;
  revenueVarianceVsBaseAssumption: number | null;
  expenseVarianceVsBaseAssumption: number | null;
}

// Feed feedback

export interface RelevanceFeedbackRequest {
  profileId: string;
  developmentId: string;
  note?: string | null;
}

// Strategy comparison

export interface CompareStrategiesRequest {
  strategyIds: string[];
}

// Action item status update

export interface ActionStatusUpdateRequest {
  status: ActionStatus;
}

// Common

export interface ApiError {
  timestamp: string;
  status: number;
  error: string;
  message: string;
  path: string;
  details: string[];
}

export interface PageResponse<T> {
  content: T[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

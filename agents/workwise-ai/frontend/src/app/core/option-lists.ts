import { BusinessType, DevelopmentCategory, Objective, RiskTolerance } from './models';

function label(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export const BUSINESS_TYPE_OPTIONS: { value: BusinessType; label: string }[] = [
  'SOLE_PROPRIETOR',
  'SMALL_BUSINESS',
  'FACTORY_WORKER_OR_SUPERVISOR',
  'SALARIED_EMPLOYEE',
  'FREELANCER',
  'OTHER'
].map((v) => ({ value: v as BusinessType, label: label(v) }));

export const OBJECTIVE_OPTIONS: { value: Objective; label: string }[] = [
  'INCREASE_INCOME',
  'INCREASE_BUSINESS_PROFIT',
  'REDUCE_EXPENSES',
  'FIND_CUSTOMERS',
  'IMPROVE_PRODUCTIVITY',
  'DISCOVER_CAREER_OPPORTUNITIES',
  'LEARN_VALUABLE_SKILLS',
  'IDENTIFY_MARKET_CHANGES',
  'IMPROVE_OPERATIONAL_EFFICIENCY'
].map((v) => ({ value: v as Objective, label: label(v) }));

export const RISK_TOLERANCE_OPTIONS: { value: RiskTolerance; label: string }[] = ['LOW', 'MEDIUM', 'HIGH'].map((v) => ({
  value: v as RiskTolerance,
  label: label(v)
}));

export const DEVELOPMENT_CATEGORY_OPTIONS: { value: DevelopmentCategory; label: string }[] = [
  'GOVERNMENT_POLICY',
  'INDUSTRY_CHANGES',
  'MARKET_PRICES',
  'BUSINESS_INVESTMENTS',
  'TECHNOLOGY',
  'SUPPLY_CHAINS',
  'WEATHER_AND_CLIMATE',
  'EMPLOYMENT',
  'CUSTOMER_DEMAND',
  'TRAINING_AND_SKILLS',
  'COMPETITOR_DEVELOPMENTS'
].map((v) => ({ value: v as DevelopmentCategory, label: label(v) }));

export function formatEnumLabel(value: string): string {
  return label(value);
}

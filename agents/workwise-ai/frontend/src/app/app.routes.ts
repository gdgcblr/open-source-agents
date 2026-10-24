import { Routes } from '@angular/router';
import { ProfilePageComponent } from './features/profile/profile-page.component';
import { FeedPageComponent } from './features/feed/feed-page.component';
import { DevelopmentDetailPageComponent } from './features/development-detail/development-detail-page.component';
import { AnalysisPageComponent } from './features/analysis/analysis-page.component';
import { StrategyComparisonPageComponent } from './features/strategy-comparison/strategy-comparison-page.component';
import { FinancialCalculatorPageComponent } from './features/financial-calculator/financial-calculator-page.component';
import { ActionPlanPageComponent } from './features/action-plan/action-plan-page.component';
import { OutcomePageComponent } from './features/outcome/outcome-page.component';

export const routes: Routes = [
  { path: '', redirectTo: 'feed', pathMatch: 'full' },
  { path: 'feed', component: FeedPageComponent },
  { path: 'profile', component: ProfilePageComponent },
  { path: 'developments/:id', component: DevelopmentDetailPageComponent },
  { path: 'analysis/:id', component: AnalysisPageComponent },
  { path: 'strategies/compare', component: StrategyComparisonPageComponent },
  { path: 'financial/:strategyId', component: FinancialCalculatorPageComponent },
  { path: 'action-plan/new/:strategyId', component: ActionPlanPageComponent },
  { path: 'action-plan/:id', component: ActionPlanPageComponent },
  { path: 'outcome/:strategyId', component: OutcomePageComponent },
  { path: '**', redirectTo: 'feed' }
];

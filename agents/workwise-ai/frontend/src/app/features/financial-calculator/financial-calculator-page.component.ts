import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { FinancialScenarioRequest, FinancialScenarioResponse } from '../../core/models';
import { FinancialService } from '../../core/services/financial.service';

@Component({
  selector: 'app-financial-calculator-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './financial-calculator-page.component.html',
  styleUrl: './financial-calculator-page.component.scss'
})
export class FinancialCalculatorPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly financialService = inject(FinancialService);

  protected strategyId = '';
  protected readonly calculating = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly scenarios = signal<FinancialScenarioResponse[]>([]);

  protected model = {
    quantity: 100,
    unitCost: 100,
    transportCost: 0,
    taxesDuties: 0,
    handlingCost: 0,
    qualityControlCost: 0,
    otherAcquisitionCost: 0,
    sellingPrice: 150,
    variableSellingCostPerUnit: 0,
    otherOperatingCost: 0,
    expectedSalesQuantity: 90,
    unsoldInventoryAssumption: 10
  };

  ngOnInit(): void {
    this.strategyId = this.route.snapshot.paramMap.get('strategyId')!;
    this.financialService.getForStrategy(this.strategyId).subscribe({
      next: (scenarios) => this.scenarios.set(scenarios),
      error: () => {
        /* no existing scenarios yet; this is expected for a new strategy */
      }
    });
  }

  calculate(): void {
    this.calculating.set(true);
    this.error.set(null);
    const request: FinancialScenarioRequest = { strategyId: this.strategyId, ...this.model };
    this.financialService.recalculate(request).subscribe({
      next: (scenarios) => {
        this.scenarios.set(scenarios);
        this.calculating.set(false);
      },
      error: (err) => {
        this.calculating.set(false);
        this.error.set(err?.error?.message ?? 'Could not calculate financial scenarios.');
      }
    });
  }

  goToActionPlan(): void {
    this.router.navigate(['/action-plan/new', this.strategyId]);
  }
}

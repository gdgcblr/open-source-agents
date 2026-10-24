import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ActionItemRequest, ActionPlanResponse, ActionStatus } from '../../core/models';
import { ActionPlanService } from '../../core/services/action-plan.service';

@Component({
  selector: 'app-action-plan-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './action-plan-page.component.html',
  styleUrl: './action-plan-page.component.scss'
})
export class ActionPlanPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly actionPlanService = inject(ActionPlanService);

  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly plan = signal<ActionPlanResponse | null>(null);
  protected readonly isNew = signal(false);

  protected strategyId = '';
  protected title = '';
  protected items: ActionItemRequest[] = [this.emptyItem()];

  protected readonly statuses: ActionStatus[] = ['NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED'];

  ngOnInit(): void {
    const strategyId = this.route.snapshot.paramMap.get('strategyId');
    const planId = this.route.snapshot.paramMap.get('id');

    if (strategyId) {
      this.strategyId = strategyId;
      this.isNew.set(true);
      this.loading.set(false);
      return;
    }

    if (planId) {
      this.actionPlanService.get(planId).subscribe({
        next: (plan) => {
          this.plan.set(plan);
          this.strategyId = plan.strategyId;
          this.loading.set(false);
        },
        error: () => {
          this.error.set('Could not load this action plan.');
          this.loading.set(false);
        }
      });
    }
  }

  private emptyItem(): ActionItemRequest {
    return { action: '', estimatedDuration: '', requiredResources: [], expectedCost: null, successMetric: '', mainRisk: '' };
  }

  addItem(): void {
    this.items.push(this.emptyItem());
  }

  removeItem(index: number): void {
    this.items.splice(index, 1);
  }

  createPlan(): void {
    this.saving.set(true);
    this.error.set(null);
    this.actionPlanService
      .create({
        strategyId: this.strategyId,
        title: this.title,
        items: this.items.filter((i) => i.action.trim().length > 0)
      })
      .subscribe({
        next: (plan) => {
          this.saving.set(false);
          this.router.navigate(['/action-plan', plan.id]);
        },
        error: (err) => {
          this.saving.set(false);
          this.error.set(err?.error?.message ?? 'Could not create the action plan.');
        }
      });
  }

  updateStatus(itemId: string, status: ActionStatus): void {
    const plan = this.plan();
    if (!plan) {
      return;
    }
    this.actionPlanService.updateItemStatus(plan.id, itemId, status).subscribe({
      next: (updated) => this.plan.set(updated),
      error: () => this.error.set('Could not update this item.')
    });
  }

  goToOutcome(): void {
    this.router.navigate(['/outcome', this.strategyId]);
  }
}

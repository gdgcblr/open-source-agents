import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { StrategyOutcomeRequest, StrategyOutcomeResponse } from '../../core/models';
import { OutcomeService } from '../../core/services/outcome.service';

@Component({
  selector: 'app-outcome-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './outcome-page.component.html',
  styleUrl: './outcome-page.component.scss'
})
export class OutcomePageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly outcomeService = inject(OutcomeService);

  protected strategyId = '';
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly history = signal<StrategyOutcomeResponse[]>([]);

  protected model: Omit<StrategyOutcomeRequest, 'strategyId'> = {
    dateStarted: null,
    dateCompleted: null,
    actualExpenses: null,
    actualRevenue: null,
    timeSpentHours: null,
    ordersReceived: null,
    customersAcquired: null,
    userReportedOutcome: '',
    lessonsLearned: ''
  };

  ngOnInit(): void {
    this.strategyId = this.route.snapshot.paramMap.get('strategyId')!;
    this.loadHistory();
  }

  private loadHistory(): void {
    this.outcomeService.history(this.strategyId).subscribe({
      next: (history) => this.history.set(history),
      error: () => {
        /* no outcomes recorded yet */
      }
    });
  }

  submit(): void {
    this.saving.set(true);
    this.error.set(null);
    this.outcomeService.record({ strategyId: this.strategyId, ...this.model }).subscribe({
      next: () => {
        this.saving.set(false);
        this.loadHistory();
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(err?.error?.message ?? 'Could not record this outcome.');
      }
    });
  }
}

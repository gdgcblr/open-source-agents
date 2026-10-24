import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AnalysisResponse, StrategyResponse } from '../../core/models';
import { AnalysisService } from '../../core/services/analysis.service';

@Component({
  selector: 'app-analysis-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './analysis-page.component.html',
  styleUrl: './analysis-page.component.scss'
})
export class AnalysisPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly analysisService = inject(AnalysisService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly analysis = signal<AnalysisResponse | null>(null);
  protected readonly strategies = signal<StrategyResponse[]>([]);
  protected readonly selectedIds = signal<Set<string>>(new Set());

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.analysisService.get(id).subscribe({
      next: (analysis) => this.analysis.set(analysis),
      error: () => this.error.set('Could not load this analysis.')
    });
    this.analysisService.getStrategies(id).subscribe({
      next: (strategies) => {
        this.strategies.set(strategies);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load strategies for this analysis.');
        this.loading.set(false);
      }
    });
  }

  toggleSelected(strategyId: string): void {
    const set = new Set(this.selectedIds());
    if (set.has(strategyId)) {
      set.delete(strategyId);
    } else {
      set.add(strategyId);
    }
    this.selectedIds.set(set);
  }

  isSelected(strategyId: string): boolean {
    return this.selectedIds().has(strategyId);
  }

  compareSelected(): void {
    const ids = Array.from(this.selectedIds());
    if (ids.length < 2) {
      this.error.set('Select at least two strategies to compare.');
      return;
    }
    this.router.navigate(['/strategies/compare'], { queryParams: { ids: ids.join(',') } });
  }
}

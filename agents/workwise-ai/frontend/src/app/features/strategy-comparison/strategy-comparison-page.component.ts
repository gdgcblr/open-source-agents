import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { StrategyComparisonItem } from '../../core/models';
import { StrategyService } from '../../core/services/strategy.service';

@Component({
  selector: 'app-strategy-comparison-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './strategy-comparison-page.component.html',
  styleUrl: './strategy-comparison-page.component.scss'
})
export class StrategyComparisonPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly strategyService = inject(StrategyService);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly items = signal<StrategyComparisonItem[]>([]);
  protected readonly selecting = signal<string | null>(null);

  ngOnInit(): void {
    const idsParam = this.route.snapshot.queryParamMap.get('ids');
    const ids = idsParam ? idsParam.split(',').filter((id) => id.length > 0) : [];
    if (ids.length < 2) {
      this.error.set('At least two strategy ids are required to compare.');
      this.loading.set(false);
      return;
    }
    this.strategyService.compare(ids).subscribe({
      next: (items) => {
        this.items.set(items);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load the comparison.');
        this.loading.set(false);
      }
    });
  }

  select(strategyId: string): void {
    this.selecting.set(strategyId);
    this.strategyService.select(strategyId).subscribe({
      next: () => {
        this.selecting.set(null);
        this.router.navigate(['/financial', strategyId]);
      },
      error: () => {
        this.selecting.set(null);
        this.error.set('Could not select this strategy.');
      }
    });
  }
}

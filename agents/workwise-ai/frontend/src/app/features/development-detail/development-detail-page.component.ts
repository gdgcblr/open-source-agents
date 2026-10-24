import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { DevelopmentResponse } from '../../core/models';
import { AnalysisService } from '../../core/services/analysis.service';
import { DevelopmentService } from '../../core/services/development.service';
import { ProfileStore } from '../../core/services/profile-store.service';

@Component({
  selector: 'app-development-detail-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './development-detail-page.component.html',
  styleUrl: './development-detail-page.component.scss'
})
export class DevelopmentDetailPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly developmentService = inject(DevelopmentService);
  private readonly analysisService = inject(AnalysisService);
  protected readonly profileStore = inject(ProfileStore);

  protected readonly loading = signal(true);
  protected readonly analyzing = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly development = signal<DevelopmentResponse | null>(null);

  async ngOnInit(): Promise<void> {
    const id = this.route.snapshot.paramMap.get('id')!;
    if (!this.profileStore.profile()) {
      await this.profileStore.load();
    }
    this.developmentService.get(id).subscribe({
      next: (dev) => {
        this.development.set(dev);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load this development.');
        this.loading.set(false);
      }
    });
  }

  analyze(): void {
    const dev = this.development();
    const profile = this.profileStore.profile();
    if (!dev || !profile) {
      return;
    }
    this.analyzing.set(true);
    this.error.set(null);
    this.analysisService.create(profile.id, dev.id).subscribe({
      next: (analysis) => {
        this.analyzing.set(false);
        this.router.navigate(['/analysis', analysis.id]);
      },
      error: (err) => {
        this.analyzing.set(false);
        this.error.set(err?.error?.message ?? 'Analysis failed. The AI provider may be unavailable.');
      }
    });
  }

  evidenceBadgeClass(state: string): string {
    switch (state) {
      case 'VERIFIED':
        return 'badge verified';
      case 'PARTIALLY_VERIFIED':
        return 'badge partial';
      case 'DEMONSTRATION_DATA':
        return 'badge demo';
      default:
        return 'badge unverified';
    }
  }
}

import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { FeedItemResponse, FeedResponse } from '../../core/models';
import { FeedService } from '../../core/services/feed.service';
import { ProfileStore } from '../../core/services/profile-store.service';

@Component({
  selector: 'app-feed-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './feed-page.component.html',
  styleUrl: './feed-page.component.scss'
})
export class FeedPageComponent implements OnInit {
  private readonly feedService = inject(FeedService);
  protected readonly profileStore = inject(ProfileStore);
  private readonly router = inject(Router);

  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly feed = signal<FeedResponse | null>(null);

  async ngOnInit(): Promise<void> {
    const profile = this.profileStore.profile() ?? (await this.profileStore.load());
    if (!profile) {
      this.loading.set(false);
      return;
    }
    this.feedService.getFeed(profile.id).subscribe({
      next: (feed) => {
        this.feed.set(feed);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Could not load your feed. Please try again later.');
        this.loading.set(false);
      }
    });
  }

  openDevelopment(item: FeedItemResponse): void {
    this.router.navigate(['/developments', item.developmentId]);
  }

  markIrrelevant(item: FeedItemResponse, event: Event): void {
    event.stopPropagation();
    const profile = this.profileStore.profile();
    if (!profile) {
      return;
    }
    this.feedService.submitFeedback({ profileId: profile.id, developmentId: item.developmentId }).subscribe(() => {
      const feed = this.feed();
      if (!feed) {
        return;
      }
      const remove = (list: FeedItemResponse[]) => list.filter((i) => i.developmentId !== item.developmentId);
      this.feed.set({
        importantForYourWork: remove(feed.importantForYourWork),
        potentialOpportunities: remove(feed.potentialOpportunities),
        trends: remove(feed.trends),
        savedAnalyses: feed.savedAnalyses
      });
    });
  }

  goToOnboarding(): void {
    this.router.navigate(['/profile']);
  }

  evidenceBadgeClass(state: FeedItemResponse['evidenceState']): string {
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

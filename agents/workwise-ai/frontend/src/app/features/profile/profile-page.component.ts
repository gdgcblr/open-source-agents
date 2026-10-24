import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  BUSINESS_TYPE_OPTIONS,
  DEVELOPMENT_CATEGORY_OPTIONS,
  OBJECTIVE_OPTIONS,
  RISK_TOLERANCE_OPTIONS
} from '../../core/option-lists';
import { UserProfileRequest, UserProfileResponse } from '../../core/models';
import { ProfileService } from '../../core/services/profile.service';
import { ProfileStore } from '../../core/services/profile-store.service';

type ProfileFormModel = UserProfileRequest & {
  secondaryObjectivesText: string;
  relevantKeywordsText: string;
  preferredCategoriesText: string[];
};

@Component({
  selector: 'app-profile-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './profile-page.component.html',
  styleUrl: './profile-page.component.scss'
})
export class ProfilePageComponent implements OnInit {
  private readonly profileService = inject(ProfileService);
  private readonly profileStore = inject(ProfileStore);
  private readonly router = inject(Router);

  protected readonly businessTypes = BUSINESS_TYPE_OPTIONS;
  protected readonly objectives = OBJECTIVE_OPTIONS;
  protected readonly riskTolerances = RISK_TOLERANCE_OPTIONS;
  protected readonly categories = DEVELOPMENT_CATEGORY_OPTIONS;

  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly saved = signal(false);
  protected existingProfileId: string | null = null;

  protected model: ProfileFormModel = this.emptyModel();

  ngOnInit(): void {
    this.loading.set(true);
    this.profileStore.load().then((profile) => {
      if (profile) {
        this.applyProfile(profile);
      }
      this.loading.set(false);
    });
  }

  private emptyModel(): ProfileFormModel {
    return {
      occupation: '',
      industry: '',
      country: '',
      region: '',
      city: '',
      businessType: 'SMALL_BUSINESS',
      primaryObjective: 'INCREASE_INCOME',
      secondaryObjectives: [],
      budgetAmount: null,
      riskTolerance: 'MEDIUM',
      relevantKeywords: [],
      preferredLanguage: 'en',
      preferredCategories: [],
      secondaryObjectivesText: '',
      relevantKeywordsText: '',
      preferredCategoriesText: []
    };
  }

  private applyProfile(profile: UserProfileResponse): void {
    this.existingProfileId = profile.id;
    this.model = {
      ...profile,
      secondaryObjectivesText: profile.secondaryObjectives.join(', '),
      relevantKeywordsText: profile.relevantKeywords.join(', '),
      preferredCategoriesText: [...profile.preferredCategories]
    };
  }

  toggleCategory(category: string): void {
    const idx = this.model.preferredCategoriesText.indexOf(category);
    if (idx >= 0) {
      this.model.preferredCategoriesText.splice(idx, 1);
    } else {
      this.model.preferredCategoriesText.push(category);
    }
  }

  isCategorySelected(category: string): boolean {
    return this.model.preferredCategoriesText.includes(category);
  }

  submit(): void {
    this.error.set(null);
    this.saved.set(false);
    this.saving.set(true);

    const request: UserProfileRequest = {
      occupation: this.model.occupation,
      industry: this.model.industry,
      country: this.model.country,
      region: this.model.region || null,
      city: this.model.city || null,
      businessType: this.model.businessType,
      primaryObjective: this.model.primaryObjective,
      secondaryObjectives: splitCsv(this.model.secondaryObjectivesText),
      budgetAmount: this.model.budgetAmount || null,
      riskTolerance: this.model.riskTolerance,
      relevantKeywords: splitCsv(this.model.relevantKeywordsText),
      preferredLanguage: this.model.preferredLanguage || 'en',
      preferredCategories: this.model.preferredCategoriesText
    };

    const result$ = this.existingProfileId
      ? this.profileService.update(this.existingProfileId, request)
      : this.profileService.create(request);

    result$.subscribe({
      next: (profile) => {
        this.applyProfile(profile);
        this.profileStore.set(profile);
        this.saving.set(false);
        this.saved.set(true);
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(err?.error?.message ?? 'Could not save profile. Please check the form and try again.');
      }
    });
  }

  goToFeed(): void {
    this.router.navigate(['/feed']);
  }
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { FeedResponse, RelevanceFeedbackRequest } from '../models';

@Injectable({ providedIn: 'root' })
export class FeedService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/feed`;

  getFeed(profileId: string): Observable<FeedResponse> {
    return this.http.get<FeedResponse>(this.baseUrl, { params: { profileId } });
  }

  submitFeedback(request: RelevanceFeedbackRequest): Observable<void> {
    return this.http.post<void>(`${this.baseUrl}/feedback`, request);
  }
}

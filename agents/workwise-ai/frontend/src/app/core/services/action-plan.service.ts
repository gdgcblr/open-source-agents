import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ActionPlanRequest, ActionPlanResponse, ActionStatus } from '../models';

@Injectable({ providedIn: 'root' })
export class ActionPlanService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/action-plans`;

  create(request: ActionPlanRequest): Observable<ActionPlanResponse> {
    return this.http.post<ActionPlanResponse>(this.baseUrl, request);
  }

  get(id: string): Observable<ActionPlanResponse> {
    return this.http.get<ActionPlanResponse>(`${this.baseUrl}/${id}`);
  }

  updateItemStatus(planId: string, itemId: string, status: ActionStatus): Observable<ActionPlanResponse> {
    return this.http.put<ActionPlanResponse>(`${this.baseUrl}/${planId}/items/${itemId}`, { status });
  }
}

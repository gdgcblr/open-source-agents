import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { StrategyComparisonItem, StrategyResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class StrategyService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/strategies`;

  get(id: string): Observable<StrategyResponse> {
    return this.http.get<StrategyResponse>(`${this.baseUrl}/${id}`);
  }

  compare(strategyIds: string[]): Observable<StrategyComparisonItem[]> {
    return this.http.post<StrategyComparisonItem[]>(`${this.baseUrl}/compare`, { strategyIds });
  }

  select(id: string): Observable<StrategyResponse> {
    return this.http.post<StrategyResponse>(`${this.baseUrl}/${id}/select`, {});
  }
}

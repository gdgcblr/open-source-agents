import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { StrategyOutcomeRequest, StrategyOutcomeResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class OutcomeService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/outcomes`;

  record(request: StrategyOutcomeRequest): Observable<StrategyOutcomeResponse> {
    return this.http.post<StrategyOutcomeResponse>(this.baseUrl, request);
  }

  history(strategyId: string): Observable<StrategyOutcomeResponse[]> {
    return this.http.get<StrategyOutcomeResponse[]>(`${this.baseUrl}/by-strategy/${strategyId}`);
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { FinancialScenarioRequest, FinancialScenarioResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class FinancialService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/financial-scenarios`;

  recalculate(request: FinancialScenarioRequest): Observable<FinancialScenarioResponse[]> {
    return this.http.post<FinancialScenarioResponse[]>(this.baseUrl, request);
  }

  getForStrategy(strategyId: string): Observable<FinancialScenarioResponse[]> {
    return this.http.get<FinancialScenarioResponse[]>(`${this.baseUrl}/by-strategy/${strategyId}`);
  }
}

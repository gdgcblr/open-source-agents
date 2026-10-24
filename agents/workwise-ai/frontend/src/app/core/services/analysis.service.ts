import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AnalysisResponse, StrategyResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class AnalysisService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/analysis`;

  create(profileId: string, developmentId: string): Observable<AnalysisResponse> {
    return this.http.post<AnalysisResponse>(this.baseUrl, { profileId, developmentId });
  }

  get(id: string): Observable<AnalysisResponse> {
    return this.http.get<AnalysisResponse>(`${this.baseUrl}/${id}`);
  }

  getStrategies(id: string): Observable<StrategyResponse[]> {
    return this.http.get<StrategyResponse[]>(`${this.baseUrl}/${id}/strategies`);
  }

  listForProfile(profileId: string): Observable<AnalysisResponse[]> {
    return this.http.get<AnalysisResponse[]>(this.baseUrl, { params: { profileId } });
  }
}

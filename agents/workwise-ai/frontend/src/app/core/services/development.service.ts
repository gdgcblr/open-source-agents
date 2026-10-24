import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { DevelopmentCategory, DevelopmentResponse, PageResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class DevelopmentService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/developments`;

  list(filters?: {
    category?: DevelopmentCategory;
    country?: string;
    region?: string;
    recencyDays?: number;
    page?: number;
    size?: number;
  }): Observable<PageResponse<DevelopmentResponse>> {
    let params = new HttpParams();
    if (filters) {
      for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined && value !== null && value !== '') {
          params = params.set(key, String(value));
        }
      }
    }
    return this.http.get<PageResponse<DevelopmentResponse>>(this.baseUrl, { params });
  }

  get(id: string): Observable<DevelopmentResponse> {
    return this.http.get<DevelopmentResponse>(`${this.baseUrl}/${id}`);
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { UserProfileRequest, UserProfileResponse } from '../models';

@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/profiles`;

  create(request: UserProfileRequest): Observable<UserProfileResponse> {
    return this.http.post<UserProfileResponse>(this.baseUrl, request);
  }

  update(id: string, request: UserProfileRequest): Observable<UserProfileResponse> {
    return this.http.put<UserProfileResponse>(`${this.baseUrl}/${id}`, request);
  }

  get(id: string): Observable<UserProfileResponse> {
    return this.http.get<UserProfileResponse>(`${this.baseUrl}/${id}`);
  }

  listMine(): Observable<UserProfileResponse[]> {
    return this.http.get<UserProfileResponse[]>(this.baseUrl);
  }
}

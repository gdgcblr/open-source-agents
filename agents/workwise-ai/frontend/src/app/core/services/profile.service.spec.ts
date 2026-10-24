import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { ProfileService } from './profile.service';
import { UserProfileResponse } from '../models';

describe('ProfileService', () => {
  let service: ProfileService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ProfileService]
    });
    service = TestBed.inject(ProfileService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('lists my profiles from /profiles', () => {
    const mockResponse: UserProfileResponse[] = [];

    service.listMine().subscribe((profiles) => {
      expect(profiles).toEqual(mockResponse);
    });

    const req = httpMock.expectOne(`${environment.apiBaseUrl}/profiles`);
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);
  });

  it('creates a profile via POST /profiles', () => {
    service
      .create({
        occupation: 'Textile Trader',
        industry: 'Textiles',
        country: 'India',
        region: null,
        city: null,
        businessType: 'SMALL_BUSINESS',
        primaryObjective: 'INCREASE_INCOME',
        secondaryObjectives: [],
        budgetAmount: null,
        riskTolerance: 'MEDIUM',
        relevantKeywords: [],
        preferredLanguage: 'en',
        preferredCategories: []
      })
      .subscribe();

    const req = httpMock.expectOne(`${environment.apiBaseUrl}/profiles`);
    expect(req.request.method).toBe('POST');
    req.flush({});
  });
});

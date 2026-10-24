import { TestBed } from '@angular/core/testing';
import { CurrentUserService, DEMO_PERSONAS } from './current-user.service';

describe('CurrentUserService', () => {
  let service: CurrentUserService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
    service = TestBed.inject(CurrentUserService);
  });

  it('defaults to the textile trader persona', () => {
    expect(service.userId()).toBe('demo-textile-trader');
  });

  it('switches persona and persists to localStorage', () => {
    service.setUserId('demo-software-engineer');
    expect(service.userId()).toBe('demo-software-engineer');
    expect(localStorage.getItem('workwise.demoUserId')).toBe('demo-software-engineer');
  });

  it('exposes both known demo personas', () => {
    expect(DEMO_PERSONAS.length).toBe(2);
  });
});

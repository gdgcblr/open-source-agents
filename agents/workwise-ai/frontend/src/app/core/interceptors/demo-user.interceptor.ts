import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { CurrentUserService } from '../services/current-user.service';

/** Attaches the X-Demo-User-Id header to every outgoing request. */
export const demoUserInterceptor: HttpInterceptorFn = (req, next) => {
  const currentUser = inject(CurrentUserService);
  const cloned = req.clone({
    setHeaders: { 'X-Demo-User-Id': currentUser.userId() }
  });
  return next(cloned);
};

package com.workwise.ai.common.auth;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Populates {@link CurrentUser} from the {@code X-Demo-User-Id} header, defaulting to the
 * configured demo user. See {@link CurrentUser} Javadoc for the documented scope/limitation of
 * this prototype authentication mechanism.
 */
@Component
public class DemoUserFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Demo-User-Id";

    private final String defaultUserId;

    public DemoUserFilter(@Value("${workwise.demo.default-user-id}") String defaultUserId) {
        this.defaultUserId = defaultUserId;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String headerValue = request.getHeader(HEADER_NAME);
        String userId = (headerValue == null || headerValue.isBlank()) ? defaultUserId : headerValue.trim();
        try {
            CurrentUser.set(userId);
            filterChain.doFilter(request, response);
        } finally {
            CurrentUser.clear();
        }
    }
}

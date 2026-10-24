package com.workwise.ai.common.auth;

/**
 * Holds the identity of the "current user" for this request.
 *
 * <p>PROTOTYPE LIMITATION: This is a documented local demo-user mechanism, not real authentication.
 * It is populated exclusively by {@link DemoUserFilter} from the {@code X-Demo-User-Id} request
 * header (or a configured default), never from a client-supplied body field that a service method
 * blindly trusts as "proof of identity" for someone else's resources. Every profile-scoped service
 * method still compares the resource's stored {@code ownerUserId} against this value before
 * allowing access/mutation, which is the behavior that would carry over unchanged once this filter
 * is replaced by real Spring Security authentication (e.g. OAuth2/JWT resource server).</p>
 */
public final class CurrentUser {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private CurrentUser() {
    }

    public static void set(String userId) {
        CURRENT.set(userId);
    }

    public static String get() {
        String userId = CURRENT.get();
        if (userId == null) {
            throw new IllegalStateException("No current user set on this thread");
        }
        return userId;
    }

    public static void clear() {
        CURRENT.remove();
    }
}

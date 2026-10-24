package com.workwise.ai.common.exception;

/** Thrown when the current demo user does not own / cannot access a resource. */
public class AccessDeniedException extends RuntimeException {
    public AccessDeniedException(String message) {
        super(message);
    }
}

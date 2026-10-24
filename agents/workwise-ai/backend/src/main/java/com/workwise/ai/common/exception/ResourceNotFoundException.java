package com.workwise.ai.common.exception;

/** Thrown when a requested resource does not exist or is not visible to the current user. */
public class ResourceNotFoundException extends RuntimeException {
    public ResourceNotFoundException(String message) {
        super(message);
    }
}

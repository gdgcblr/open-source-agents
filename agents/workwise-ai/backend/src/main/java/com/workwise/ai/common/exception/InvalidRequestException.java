package com.workwise.ai.common.exception;

/** Thrown when input is semantically invalid beyond simple bean-validation (e.g. incomplete financial inputs). */
public class InvalidRequestException extends RuntimeException {
    public InvalidRequestException(String message) {
        super(message);
    }
}

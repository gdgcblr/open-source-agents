package com.workwise.ai.common.exception;

/** Thrown when a configured AI provider (e.g. real LLM) cannot complete a request. */
public class AiProviderException extends RuntimeException {
    public AiProviderException(String message) {
        super(message);
    }

    public AiProviderException(String message, Throwable cause) {
        super(message, cause);
    }
}

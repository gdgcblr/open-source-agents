package com.workwise.ai.sources.adapter;

/** Raised when a configured source could not be reached or parsed; never swallowed into fabricated data. */
public class SourceUnavailableException extends Exception {
    public SourceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }

    public SourceUnavailableException(String message) {
        super(message);
    }
}

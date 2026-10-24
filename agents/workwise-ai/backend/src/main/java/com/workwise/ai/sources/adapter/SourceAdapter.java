package com.workwise.ai.sources.adapter;

import com.workwise.ai.sources.domain.InformationSource;
import com.workwise.ai.sources.domain.SourceType;

import java.util.List;

/**
 * Strategy interface for pulling raw items from an {@link InformationSource}.
 * Implementations must only access permitted, configured sources — never scrape arbitrary sites
 * or private accounts, and must raise {@link SourceUnavailableException} rather than silently
 * returning fabricated data when a source cannot be reached.
 */
public interface SourceAdapter {

    SourceType supportedType();

    List<RawDevelopmentItem> fetch(InformationSource source) throws SourceUnavailableException;
}

package com.workwise.ai.news.domain;

/**
 * Evidence/verification state for a {@link Development}.
 *
 * <ul>
 *   <li>{@code DEMONSTRATION_DATA} — fictional illustrative content seeded for the prototype demo;
 *       never real-world fact, always labeled as such in every DTO.</li>
 *   <li>{@code UNVERIFIED} — reported by exactly one configured source (e.g. a single RSS feed);
 *       presence in a feed is not independent verification of its claims.</li>
 *   <li>{@code PARTIALLY_VERIFIED} — a second, independent configured source reports a materially
 *       similar claim (matched by the ingestion module's simple title/entity overlap heuristic).</li>
 *   <li>{@code VERIFIED} — in addition to the partially-verified condition, at least one
 *       contributing source is flagged {@code authoritative=true} on {@link
 *       com.workwise.ai.sources.domain.InformationSource}.</li>
 * </ul>
 */
public enum EvidenceState {
    UNVERIFIED,
    PARTIALLY_VERIFIED,
    VERIFIED,
    DEMONSTRATION_DATA
}

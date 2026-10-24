package dev.mutationaudit;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Element;

/** Parses PIT XML without resolving external entities. Scores preserve PIT's detected flag. */
public record MutationReport(List<Mutant> mutants) {
    public record Mutant(String status, boolean detected, String sourceFile, String className,
                         String method, int line, String mutator, String description) {}

    private static final Set<String> STATUSES = Set.of("KILLED", "SURVIVED", "NO_COVERAGE", "TIMED_OUT",
            "NON_VIABLE", "MEMORY_ERROR", "NOT_STARTED", "STARTED", "RUN_ERROR", "EQUIVALENT");

    public MutationReport { mutants = List.copyOf(mutants); }

    public static MutationReport read(Path file) throws Exception {
        if (Files.size(file) > 50_000_000) throw new IllegalArgumentException("PIT XML exceeds 50 MB.");
        var factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        var document = factory.newDocumentBuilder().parse(file.toFile());
        if (!document.getDocumentElement().getTagName().equals("mutations"))
            throw new IllegalArgumentException("Expected a PIT <mutations> report.");
        var rows = document.getDocumentElement().getElementsByTagName("mutation");
        var mutants = new ArrayList<Mutant>();
        for (int i = 0; i < rows.getLength(); i++) {
            var row = (Element) rows.item(i);
            String status = row.getAttribute("status");
            if (!STATUSES.contains(status)) throw new IllegalArgumentException("Unknown PIT status: " + status);
            String detected = row.getAttribute("detected");
            if (!Set.of("true", "false").contains(detected))
                throw new IllegalArgumentException("Missing or invalid detected attribute.");
            mutants.add(new Mutant(status, Boolean.parseBoolean(detected), text(row, "sourceFile"),
                    text(row, "mutatedClass"), text(row, "mutatedMethod"), Integer.parseInt(text(row, "lineNumber")),
                    text(row, "mutator"), text(row, "description")));
        }
        return new MutationReport(mutants);
    }

    private static String text(Element element, String tag) {
        var nodes = element.getElementsByTagName(tag);
        if (nodes.getLength() != 1) throw new IllegalArgumentException("Expected one " + tag + " in mutation.");
        return nodes.item(0).getTextContent();
    }

    public Map<String, Long> counts() {
        var counts = new TreeMap<String, Long>();
        mutants.forEach(m -> counts.merge(m.status(), 1L, Long::sum));
        return counts;
    }

    public boolean complete() {
        return mutants.stream().noneMatch(m -> Set.of("STARTED", "NOT_STARTED", "RUN_ERROR").contains(m.status()));
    }

    public Double mutationScore() {
        return mutants.isEmpty() || !complete() ? null
                : 100.0 * mutants.stream().filter(Mutant::detected).count() / mutants.size();
    }

    public List<Mutant> findings() {
        return mutants.stream().filter(m -> Set.of("SURVIVED", "NO_COVERAGE").contains(m.status())).toList();
    }

    public Map<String, Object> summary() {
        var result = new LinkedHashMap<String, Object>();
        result.put("engine", "PIT");
        result.put("totalMutants", mutants.size());
        result.put("complete", complete());
        result.put("mutationScore", mutationScore());
        result.put("scoreDefinition", "100 * count(detected=true) / total PIT XML mutations; null for empty/incomplete reports");
        result.put("counts", counts());
        result.put("mutants", mutants);
        return result;
    }

    public String consoleSummary() {
        var counts = counts();
        var out = new StringBuilder("\nMutation score: ").append(mutationScore() == null ? "N/A" : String.format(Locale.ROOT, "%.1f%%", mutationScore()))
                .append("\n").append(mutants.size()).append(" mutations | ").append(counts.getOrDefault("KILLED", 0L))
                .append(" caught by tests | ").append(counts.getOrDefault("SURVIVED", 0L)).append(" survived | ")
                .append(counts.getOrDefault("NO_COVERAGE", 0L)).append(" uncovered\n");
        counts.forEach((status, count) -> {
            if (!Set.of("KILLED", "SURVIVED", "NO_COVERAGE").contains(status)) out.append(status).append(": ").append(count).append('\n');
        });
        if (!complete()) out.append("Analysis is incomplete; no reliable score is available.\n");
        if (mutants.isEmpty()) out.append("No mutations were assessed; there is no score to interpret.\n");
        if (findings().isEmpty() && !mutants.isEmpty()) out.append("No surviving or uncovered mutations were reported.\n");
        if (!findings().isEmpty()) {
            out.append("\nFirst findings:\n");
            findings().stream().limit(3).forEach(m -> out.append("  ").append(m.className()).append('.').append(m.method())
                    .append(" (line ").append(m.line()).append("): ").append(m.description()).append('\n'));
            out.append("Review these test gaps in report.md.\n");
        }
        out.append("Score reflects PIT detection flags; a high score does not guarantee safe changes.\n");
        return out.toString();
    }

    public String markdown() {
        var score = mutationScore();
        var out = new StringBuilder("# Mutation Auditor\n\nMutation score: ")
                .append(score == null ? "N/A" : String.format(Locale.ROOT, "%.1f%%", score))
                .append("\n\nTotal mutants: ").append(mutants.size()).append("\n\n");
        counts().forEach((status, count) -> out.append("- ").append(status).append(": ").append(count).append('\n'));
        out.append("\nScore uses PIT's detected flag, which can include timeouts and error outcomes, not only failing assertions. "
                + "Inspect status counts before drawing conclusions. Empty/incomplete reports have no score. "
                + "Scope is the supplied PIT report; this is not a guarantee of safe changes.\n\n## Findings\n\n");
        if (findings().isEmpty()) out.append("No surviving or uncovered mutants in this report.\n");
        findings().stream().limit(100).forEach(m -> out.append("- ").append(m.status()).append(" `")
                .append(m.className().replace('`', '_')).append('.').append(m.method().replace('`', '_'))
                .append("` line ").append(m.line()).append(": ")
                .append(m.description().replace('\n', ' ').replace('\r', ' ')).append('\n'));
        if (findings().size() > 100) out.append("\nShowing first 100 findings; JSON includes all mutants.\n");
        return out.toString();
    }
}

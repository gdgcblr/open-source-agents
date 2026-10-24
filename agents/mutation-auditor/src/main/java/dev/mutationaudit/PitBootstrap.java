package dev.mutationaudit;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

/** Produces an analysis-only POM beside the copied POM. Never edits the input project. */
final class PitBootstrap {
    static final String JUNIT_PLUGIN_VERSION = "1.2.3";

    static Path prepare(Path project) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        var doc = factory.newDocumentBuilder().parse(project.resolve("pom.xml").toFile());
        var root = doc.getDocumentElement();
        var plugins = ensure(ensure(root, "build"), "plugins");
        Element pit = children(plugins, "plugin").stream().filter(PitBootstrap::isPit).findFirst().orElse(null);
        if (pit == null) {
            pit = append(plugins, "plugin");
            value(pit, "groupId", "org.pitest");
            value(pit, "artifactId", "pitest-maven");
        }

        // Update matching build/pluginManagement/profile entries too, so active profiles do not
        // restore a stale JUnit adapter or turn this run into a dry run. No new profile is activated:
        // doing so would deactivate the project's own activeByDefault profiles.
        var all = doc.getElementsByTagNameNS("*", "plugin");
        var matches = new ArrayList<Element>();
        for (int i = 0; i < all.getLength(); i++) {
            var candidate = (Element) all.item(i);
            Node container = candidate.getParentNode();
            if (name(container).equals("plugins") && container.getParentNode() != null
                    && List.of("build", "pluginManagement").contains(name(container.getParentNode())) && isPit(candidate))
                matches.add(candidate);
        }
        for (var plugin : matches) configure(plugin, project);

        var transformers = TransformerFactory.newInstance();
        transformers.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        transformers.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
        var transformer = transformers.newTransformer();
        transformer.setOutputProperty(OutputKeys.INDENT, "yes");
        Path generated = project.resolve(".mutation-auditor-pom.xml");
        transformer.transform(new DOMSource(doc), new StreamResult(generated.toFile()));
        return generated;
    }

    private static void configure(Element plugin, Path project) {
        value(plugin, "version", ProjectRunner.PIT_VERSION);
        var configuration = ensure(plugin, "configuration");
        value(configuration, "skip", "false");
        value(configuration, "dryRun", "false");
        value(configuration, "withHistory", "false");
        value(configuration, "timestampedReports", "false");
        value(configuration, "reportsDirectory", project.resolve("target/auditor-pit").toString());
        for (String threshold : List.of("mutationThreshold", "coverageThreshold", "testStrengthThreshold"))
            value(configuration, threshold, "0");
        var formats = ensure(configuration, "outputFormats");
        formats.setTextContent("");
        formats.setAttribute("combine.self", "override");
        append(formats, "param").setTextContent("XML");
        append(formats, "param").setTextContent("HTML");
        var dependencies = ensure(plugin, "dependencies");
        for (var dep : children(dependencies, "dependency")) {
            if (text(dep, "groupId").equals("org.pitest") && text(dep, "artifactId").equals("pitest-junit5-plugin"))
                dependencies.removeChild(dep);
        }
        var adapter = append(dependencies, "dependency");
        value(adapter, "groupId", "org.pitest");
        value(adapter, "artifactId", "pitest-junit5-plugin");
        value(adapter, "version", JUNIT_PLUGIN_VERSION);
    }

    private static boolean isPit(Element plugin) {
        return text(plugin, "groupId").equals("org.pitest") && text(plugin, "artifactId").equals("pitest-maven");
    }

    private static String name(Node node) { return node.getLocalName() == null ? node.getNodeName() : node.getLocalName(); }
    private static List<Element> children(Element parent, String name) {
        var result = new ArrayList<Element>();
        for (Node n = parent.getFirstChild(); n != null; n = n.getNextSibling())
            if (n instanceof Element e && name(e).equals(name)) result.add(e);
        return result;
    }
    private static String text(Element parent, String name) {
        return children(parent, name).stream().findFirst().map(Element::getTextContent).orElse("").strip();
    }
    private static Element ensure(Element parent, String name) {
        return children(parent, name).stream().findFirst().orElseGet(() -> append(parent, name));
    }
    private static Element append(Element parent, String name) {
        Document doc = parent.getOwnerDocument();
        String prefix = parent.getPrefix();
        Element element = doc.createElementNS(parent.getNamespaceURI(), prefix == null ? name : prefix + ":" + name);
        parent.appendChild(element);
        return element;
    }
    private static void value(Element parent, String name, String value) {
        children(parent, name).forEach(parent::removeChild);
        append(parent, name).setTextContent(value);
    }
}

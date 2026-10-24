package dev.mutationaudit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import static org.junit.jupiter.api.Assertions.*;

class PitBootstrapTest {
    @TempDir Path temp;

    private Document prepare(String pom) throws Exception {
        Path original = temp.resolve("pom.xml");
        Files.writeString(original, pom);
        Path generated = PitBootstrap.prepare(temp);
        assertEquals(pom, Files.readString(original), "The input POM must remain byte-for-byte unchanged");
        assertNotEquals(original, generated);
        var factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        return factory.newDocumentBuilder().parse(generated.toFile());
    }

    private String text(Document doc, String tag, int index) {
        return doc.getElementsByTagNameNS("*", tag).item(index).getTextContent().strip();
    }

    private void assertVersions(Document doc) throws Exception {
        var xpath = XPathFactory.newInstance().newXPath();
        assertEquals(ProjectRunner.PIT_VERSION, xpath.evaluate("string((//*[local-name()='plugin' and *[local-name()='artifactId']='pitest-maven'])[1]/*[local-name()='version'])", doc));
        assertEquals(PitBootstrap.JUNIT_PLUGIN_VERSION, xpath.evaluate("string((//*[local-name()='dependency' and *[local-name()='artifactId']='pitest-junit5-plugin'])[1]/*[local-name()='version'])", doc));
    }

    @Test void provisionsPitAndJUnitAdapterWithoutAnyExistingBuildConfiguration() throws Exception {
        var doc = prepare("<project><modelVersion>4.0.0</modelVersion><artifactId>app</artifactId></project>");
        assertEquals("org.pitest", text(doc, "groupId", 0));
        assertEquals("pitest-maven", text(doc, "artifactId", 1));
        assertVersions(doc);
        assertEquals("pitest-junit5-plugin", text(doc, "artifactId", 2));
        assertEquals("false", text(doc, "dryRun", 0));
        assertEquals("XML", text(doc, "param", 0));
    }

    @Test void supportsNamespacedPomsAndKeepsApplicationDependenciesAndBuildPlugins() throws Exception {
        var doc = prepare("""
                <project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
                <dependencies><dependency><groupId>example</groupId><artifactId>app-library</artifactId><version>1</version></dependency></dependencies>
                <build><plugins><plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version><configuration><argLine>-Xmx256m</argLine></configuration></plugin></plugins></build></project>
                """);
        assertEquals(2, doc.getElementsByTagNameNS("*", "plugin").getLength());
        assertEquals("app-library", text(doc, "artifactId", 0));
        assertEquals("-Xmx256m", text(doc, "argLine", 0));
        assertEquals(0, doc.getElementsByTagNameNS("*", "profile").getLength());
        assertEquals("http://maven.apache.org/POM/4.0.0", doc.getElementsByTagNameNS("*", "dryRun").item(0).getNamespaceURI());
    }

    @Test void existingPitFiltersAreKeptButOperationalSettingsAndJUnitVersionAreUpdated() throws Exception {
        var doc = prepare("""
                <project><build><plugins><plugin><groupId>org.pitest</groupId><artifactId>pitest-maven</artifactId><version>1.0</version>
                <configuration><targetClasses><param>example.domain.*</param></targetClasses><dryRun>true</dryRun><skip>true</skip>
                <mutationThreshold>99</mutationThreshold><outputFormats><param>CSV</param></outputFormats></configuration>
                <dependencies><dependency><groupId>org.pitest</groupId><artifactId>pitest-junit5-plugin</artifactId><version>0.1</version></dependency></dependencies>
                </plugin></plugins></build></project>
                """);
        assertEquals(1, doc.getElementsByTagNameNS("*", "plugin").getLength());
        assertEquals(1, doc.getElementsByTagNameNS("*", "dependency").getLength());
        assertEquals("example.domain.*", text(doc, "param", 0));
        assertEquals("false", text(doc, "dryRun", 0));
        assertEquals("false", text(doc, "skip", 0));
        assertEquals("0", text(doc, "mutationThreshold", 0));
        assertVersions(doc);
    }

    @Test void updatesPitInsideExistingProfilesWithoutActivatingANewProfile() throws Exception {
        var doc = prepare("""
                <project><profiles><profile><id>existing-default</id><activation><activeByDefault>true</activeByDefault></activation>
                <build><plugins><plugin><groupId>org.pitest</groupId><artifactId>pitest-maven</artifactId><version>1.0</version>
                <configuration><dryRun>true</dryRun><targetClasses><param>domain.*</param></targetClasses></configuration>
                </plugin></plugins></build></profile></profiles></project>
                """);
        assertEquals(1, doc.getElementsByTagNameNS("*", "profile").getLength());
        assertEquals("existing-default", text(doc, "id", 0));
        assertEquals("true", text(doc, "activeByDefault", 0));
        assertEquals(2, doc.getElementsByTagNameNS("*", "plugin").getLength());
        assertEquals("false", text(doc, "dryRun", 0));
        assertEquals("false", text(doc, "dryRun", 1));
    }

    @Test void rejectsExternalEntitiesBeforeGeneratingAnalysisPom() throws Exception {
        assertThrows(Exception.class, () -> prepare("<!DOCTYPE project [<!ENTITY x SYSTEM 'file:///not-allowed'>]><project>&x;</project>"));
        assertFalse(Files.exists(temp.resolve(".mutation-auditor-pom.xml")));
    }
}

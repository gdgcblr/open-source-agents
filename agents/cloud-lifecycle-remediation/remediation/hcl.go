package remediation

import (
	"fmt"
	"regexp"
	"strings"
)

var resourceHeaderRE = regexp.MustCompile(`resource\s+"([^"]+)"\s+"([^"]+)"\s*\{`)

// findResourceBlock returns the byte range [start, end) of a resource block body including outer braces.
func findResourceBlock(content, resourceType, resourceName string) (start, end int, ok bool) {
	pattern := fmt.Sprintf(`resource\s+"%s"\s+"%s"\s*\{`, regexp.QuoteMeta(resourceType), regexp.QuoteMeta(resourceName))
	loc := regexp.MustCompile(pattern).FindStringIndex(content)
	if loc == nil {
		return 0, 0, false
	}
	openBrace := strings.Index(content[loc[0]:], "{")
	if openBrace < 0 {
		return 0, 0, false
	}
	bodyStart := loc[0] + openBrace
	depth := 0
	for i := bodyStart; i < len(content); i++ {
		switch content[i] {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return loc[0], i + 1, true
			}
		}
	}
	return 0, 0, false
}

func parseResourceAddress(address string) (resourceType, resourceName string, err error) {
	parts := strings.SplitN(address, ".", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", fmt.Errorf("invalid terraform address %q: expected type.name", address)
	}
	return parts[0], parts[1], nil
}

func extractAttribute(block, attrName string) string {
	re := regexp.MustCompile(`(?m)^\s*` + regexp.QuoteMeta(attrName) + `\s*=\s*"([^"]+)"`)
	m := re.FindStringSubmatch(block)
	if len(m) < 2 {
		re = regexp.MustCompile(`(?m)^\s*` + regexp.QuoteMeta(attrName) + `\s*=\s*([0-9.]+)`)
		m = re.FindStringSubmatch(block)
	}
	if len(m) < 2 {
		return ""
	}
	return m[1]
}

func extractPrimaryValue(block, attrName string) string {
	if attrName == "instance_types" {
		return extractInstanceTypes(block)
	}
	return extractAttribute(block, attrName)
}

func setPrimaryValue(block, attrName, newValue string) (string, bool) {
	if attrName == "instance_types" {
		return setInstanceTypesInBlock(block, newValue)
	}
	return setAttributeInBlock(block, attrName, newValue)
}

func extractInstanceTypes(block string) string {
	re := regexp.MustCompile(`(?m)instance_types\s*=\s*\[\s*"([^"]+)"`)
	m := re.FindStringSubmatch(block)
	if len(m) < 2 {
		return ""
	}
	return m[1]
}

func setInstanceTypesInBlock(block, newType string) (string, bool) {
	re := regexp.MustCompile(`(?m)^(\s*instance_types\s*=\s*)\[[^\]]*\]`)
	if re.FindStringIndex(block) == nil {
		return block, false
	}
	return re.ReplaceAllString(block, `${1}["`+newType+`"]`), true
}

func setAttributeInBlock(block, attrName, newValue string) (string, bool) {
	quoted := regexp.MustCompile(`(?m)^(\s*` + regexp.QuoteMeta(attrName) + `\s*=\s*)"([^"]+)"`)
	if quoted.FindStringIndex(block) != nil {
		return quoted.ReplaceAllString(block, `${1}"`+newValue+`"`), true
	}
	unquoted := regexp.MustCompile(`(?m)^(\s*` + regexp.QuoteMeta(attrName) + `\s*=\s*)([0-9.]+)`)
	if unquoted.FindStringIndex(block) != nil {
		return unquoted.ReplaceAllString(block, `${1}`+newValue), true
	}
	return block, false
}

func listResources(content string) []struct{ Type, Name string } {
	matches := resourceHeaderRE.FindAllStringSubmatch(content, -1)
	out := make([]struct{ Type, Name string }, 0, len(matches))
	for _, m := range matches {
		if len(m) >= 3 {
			out = append(out, struct{ Type, Name string }{Type: m[1], Name: m[2]})
		}
	}
	return out
}

func relatedResourceTypes(primaryType string) map[string]bool {
	switch primaryType {
	case "aws_eks_cluster":
		return map[string]bool{"aws_eks_addon": true}
	case "aws_db_instance":
		return map[string]bool{"aws_db_parameter_group": true}
	default:
		return nil
	}
}

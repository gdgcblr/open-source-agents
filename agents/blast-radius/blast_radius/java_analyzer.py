"""Java source code analyzer for method boundaries and call site discovery."""

import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from .models import JavaMethod, CallerReference

PACKAGE_PATTERN = re.compile(r"^\s*package\s+([\w\.]+)\s*;")
CLASS_PATTERN = re.compile(
    r"(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+|static\s+)*"
    r"(?:class|interface|record|enum)\s+(\w+)"
)
ANNOTATION_PATTERN = re.compile(r"^\s*@(\w+)(?:\(.*\))?")

# Matches Java method or constructor declarations
METHOD_HEADER_PATTERN = re.compile(
    r"^\s*(?:(public|protected|private|static|final|synchronized|abstract|default|native)\s+)*"
    r"(?:<[\w\s,extends?]+>\s+)?"  # generic type parameters
    r"(?:([\w\<\>\[\],\s\.\?]+)\s+)?"  # return type (None for constructor)
    r"(\w+)\s*\(([^)]*)\)"  # method name and parameters
    r"(?:\s*throws\s+[\w\s,]+)?"  # throws clause
    r"\s*(\{?|;)"  # opens body or terminates (abstract/interface)
)

KEYWORDS_NOT_METHODS = {
    "if", "for", "while", "switch", "catch", "synchronized", "record", "class", "interface", "enum"
}


JAVA_MODIFIERS = [
    "public", "protected", "private", "static", "final",
    "synchronized", "abstract", "default", "native"
]


class JavaAnalyzer:
    """Extracts Java classes, methods, and discovers call references."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self._file_cache: Dict[Path, List[JavaMethod]] = {}
        self._content_cache: Dict[Path, List[str]] = {}
        self._file_list_cache: Optional[List[Path]] = None

    def find_all_java_files(self) -> List[Path]:
        """Finds all .java files under repo root, ignoring build/cache directories."""
        if self._file_list_cache is not None:
            return self._file_list_cache

        ignore_dirs = {".git", ".idea", ".vscode", "target", "build", "node_modules", "bin"}
        java_files = []
        for p in self.repo_root.rglob("*.java"):
            parts = set(p.parts)
            if not parts.intersection(ignore_dirs):
                java_files.append(p)
        self._file_list_cache = sorted(java_files)
        return self._file_list_cache

    def parse_file(self, file_path: Path) -> List[JavaMethod]:
        """Parses a Java file and returns all declared methods and constructors."""
        path_key = file_path.resolve()
        if path_key in self._file_cache:
            return self._file_cache[path_key]

        if not file_path.exists():
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        lines = content.splitlines()
        self._content_cache[path_key] = lines
        package_name = ""
        current_class = ""
        methods: List[JavaMethod] = []

        # First pass: find package
        for line in lines:
            pkg_match = PACKAGE_PATTERN.match(line)
            if pkg_match:
                package_name = pkg_match.group(1)
                break

        # Track brace depth and token scanning
        brace_depth = 0
        in_multiline_comment = False
        pending_annotations: List[str] = []
        class_stack: List[Tuple[str, int]] = []  # (class_name, depth_at_class_start)

        # For multi-line method headers
        header_buffer = ""
        header_start_line = 0
        in_header = False

        for line_num_1, raw_line in enumerate(lines, start=1):
            cleaned, in_multiline_comment = self._strip_comments_and_strings(
                raw_line, in_multiline_comment
            )

            # Check annotations if we are at depth >= 1 or class level
            anno_match = ANNOTATION_PATTERN.match(raw_line)
            if anno_match and not in_header:
                pending_annotations.append(anno_match.group(1))

            # Detect class declaration
            class_match = CLASS_PATTERN.search(cleaned)
            if class_match and not in_header:
                c_name = class_match.group(1)
                if c_name not in KEYWORDS_NOT_METHODS:
                    current_class = c_name
                    class_stack.append((c_name, brace_depth))

            # Detect method declarations
            # Methods typically occur inside a class (brace_depth >= 1)
            stripped_line = cleaned.strip()
            if not in_header and len(class_stack) > 0 and stripped_line:
                # Check if line looks like start of a method signature
                if "(" in stripped_line and not any(stripped_line.startswith(kw + " ") or stripped_line.startswith(kw + "(") for kw in KEYWORDS_NOT_METHODS):
                    in_header = True
                    header_buffer = stripped_line
                    header_start_line = line_num_1
            elif in_header:
                header_buffer += " " + stripped_line

            if in_header and (")" in header_buffer and ("{" in header_buffer or ";" in header_buffer)):
                # Evaluate full header
                method_obj = self._match_method(
                    header_buffer=header_buffer,
                    start_line=header_start_line,
                    end_line=line_num_1,  # will be updated when method closes
                    class_name=class_stack[-1][0] if class_stack else "UnknownClass",
                    package_name=package_name,
                    file_path=str(file_path.relative_to(self.repo_root) if file_path.is_relative_to(self.repo_root) else file_path),
                    annotations=list(pending_annotations)
                )
                if method_obj:
                    methods.append(method_obj)
                pending_annotations.clear()
                in_header = False
                header_buffer = ""

            # Update brace depth
            brace_delta = cleaned.count("{") - cleaned.count("}")
            brace_depth += brace_delta

            # If brace depth closed a method
            if methods and methods[-1].end_line == header_start_line:
                # Still open, check if it closed
                # A method starts when depth was increased by its '{'
                pass

            # Manage class stack when closing braces
            while class_stack and brace_depth <= class_stack[-1][1]:
                class_stack.pop()

        # Refine method end lines using accurate brace tracking
        self._refine_method_boundaries(lines, methods)
        self._file_cache[path_key] = methods
        return methods

    def find_methods_in_diff(self, file_path_rel: str, modified_lines: Set[int]) -> List[JavaMethod]:
        """Finds which methods in the given file overlap with the modified line set."""
        full_path = self.repo_root / file_path_rel
        if not full_path.exists():
            return []

        all_methods = self.parse_file(full_path)
        impacted: List[JavaMethod] = []

        for m in all_methods:
            if any(m.start_line <= line <= m.end_line for line in modified_lines):
                impacted.append(m)

        return impacted

    def find_direct_callers(self, target_method_name: str, target_class_name: Optional[str] = None) -> List[CallerReference]:
        """Searches repository Java files for direct invocations of target_method_name."""
        callers: List[CallerReference] = []
        call_regex = re.compile(rf"(?:(\w+)\s*\.\s*)?({re.escape(target_method_name)})\s*\(")

        for file_path in self.find_all_java_files():
            file_methods = self.parse_file(file_path)
            lines = self._content_cache.get(file_path.resolve())
            if lines is None:
                continue

            rel_path = str(file_path.relative_to(self.repo_root) if file_path.is_relative_to(self.repo_root) else file_path)
            is_test_file = "test" in rel_path.lower() or file_path.name.endswith("Test.java") or file_path.name.endswith("Tests.java")

            in_multiline = False
            for line_idx, raw_line in enumerate(lines, start=1):
                clean_line, in_multiline = self._strip_comments_and_strings(raw_line, in_multiline)
                if not clean_line.strip():
                    continue

                for match in call_regex.finditer(clean_line):
                    caller_var = match.group(1)  # e.g., 'paymentClient' in paymentClient.processPayment(...)

                    # Identify enclosing method
                    enclosing_method = "TopLevel"
                    enclosing_class = file_path.stem
                    is_test_method = is_test_file
                    is_own_declaration = False

                    for m in file_methods:
                        if m.start_line <= line_idx <= m.end_line:
                            # If this line is the method's own declaration start line, skip it
                            if m.method_name == target_method_name and line_idx == m.start_line and not caller_var:
                                is_own_declaration = True
                                break
                            enclosing_method = m.method_name
                            enclosing_class = m.class_name
                            if "Test" in m.annotations or "ParameterizedTest" in m.annotations or is_test_file:
                                is_test_method = True
                            break

                    if is_own_declaration:
                        continue

                    # If line is outside any method and has no caller_var, check if it's a declaration header
                    if enclosing_method == "TopLevel" and not caller_var:
                        if self._is_declaration_line(clean_line, target_method_name, file_path.stem):
                            continue

                    callers.append(CallerReference(
                        caller_file=rel_path,
                        caller_class=enclosing_class,
                        caller_method=enclosing_method,
                        call_line=line_idx,
                        target_method_name=target_method_name,
                        target_class_hint=caller_var,
                        code_snippet=raw_line.strip(),
                        is_test=is_test_method
                    ))

        return callers

    def _match_method(
        self,
        header_buffer: str,
        start_line: int,
        end_line: int,
        class_name: str,
        package_name: str,
        file_path: str,
        annotations: List[str]
    ) -> Optional[JavaMethod]:
        """Constructs a JavaMethod if header matches a valid method or constructor."""
        # Clean extra whitespace
        norm_header = " ".join(header_buffer.split())
        match = METHOD_HEADER_PATTERN.search(norm_header)
        if not match:
            return None

        # Extract all modifiers appearing before '('
        open_paren_idx = norm_header.find("(")
        prefix = norm_header[:open_paren_idx] if open_paren_idx != -1 else norm_header
        tokens = prefix.split()
        modifiers = [m for m in JAVA_MODIFIERS if m in tokens]

        ret_type = match.group(2).strip() if match.group(2) else ""
        name = match.group(3).strip()
        params = match.group(4).strip()

        if name in KEYWORDS_NOT_METHODS:
            return None

        is_constructor = (name == class_name)
        if is_constructor:
            ret_type = "void"

        sig = f"{name}({params})"

        return JavaMethod(
            package_name=package_name,
            class_name=class_name,
            method_name=name,
            signature=sig,
            return_type=ret_type,
            modifiers=modifiers,
            annotations=annotations,
            start_line=start_line,
            end_line=end_line,
            file_path=file_path,
            is_constructor=is_constructor
        )

    def _refine_method_boundaries(self, lines: List[str], methods: List[JavaMethod]) -> None:
        """Determines precise method end lines by tracking nested brace counts from start_line."""
        for m in methods:
            # Find the opening brace '{'
            open_found = False
            depth = 0
            in_multiline = False

            for l_idx in range(m.start_line - 1, len(lines)):
                raw = lines[l_idx]
                clean, in_multiline = self._strip_comments_and_strings(raw, in_multiline)

                if not open_found:
                    if "{" in clean:
                        open_found = True
                        depth += clean.count("{") - clean.count("}")
                        if depth <= 0:
                            m.end_line = l_idx + 1
                            break
                    elif ";" in clean:
                        # Abstract or interface method with no body
                        m.end_line = l_idx + 1
                        break
                else:
                    depth += clean.count("{") - clean.count("}")
                    if depth <= 0:
                        m.end_line = l_idx + 1
                        break

    @staticmethod
    def _is_declaration_line(clean_line: str, method_name: str, class_name: str = "") -> bool:
        """Heuristic to check if a line is a method declaration rather than an invocation."""
        if "=" in clean_line:
            return False
        # Constructor check
        if class_name and method_name == class_name:
            pattern = rf"^\s*(?:(?:public|protected|private)\s+)?{re.escape(method_name)}\s*\("
            return bool(re.search(pattern, clean_line))

        # Standard method: must have return type
        pattern = rf"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|default|native)\s+)*(?:[\w\<\>\[\],\s\.\?]+\s+){re.escape(method_name)}\s*\("
        return bool(re.search(pattern, clean_line))

    @staticmethod
    def _strip_comments_and_strings(line: str, in_multiline: bool) -> Tuple[str, bool]:
        """Strips comments and literal strings from a line to prevent false brace counts."""
        result = []
        i = 0
        n = len(line)

        while i < n:
            if in_multiline:
                end_pos = line.find("*/", i)
                if end_pos != -1:
                    in_multiline = False
                    i = end_pos + 2
                else:
                    break
            else:
                if line.startswith("/*", i):
                    in_multiline = True
                    i += 2
                elif line.startswith("//", i):
                    break
                elif line[i] == '"':
                    # Skip string literal
                    i += 1
                    while i < n:
                        if line[i] == '\\':
                            i += 2  # skip escaped char
                        elif line[i] == '"':
                            i += 1
                            break
                        else:
                            i += 1
                elif line[i] == "'":
                    # Skip char literal
                    i += 1
                    while i < n:
                        if line[i] == '\\':
                            i += 2
                        elif line[i] == "'":
                            i += 1
                            break
                        else:
                            i += 1
                else:
                    result.append(line[i])
                    i += 1

        return "".join(result), in_multiline

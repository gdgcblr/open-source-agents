// AST taint helpers shared by the rce-sentinel ESLint rules.
// classify() answers: is this expression constant, attacker-tainted, or unknown?

const SOURCES = [
  /^(req|request)\.(query|body|params|headers|cookies)\b/,
  /^ctx\.(query|params|request)\b/,
  /^process\.(argv|env)\b/,
  /^(window\.)?location\.(hash|search|href)\b/,
  /^(event|e|msg)\.data\b/,
];
const SOURCE_CALLS = [/^fs\.readFileSync$/, /^(req|request)\.(get|header|param)$/];
const SANITIZERS = new Set(["Number", "parseInt", "parseFloat", "Boolean", "encodeURIComponent"]);
const MAX_DEPTH = 6;

const RANK = { constant: 0, unknown: 1, tainted: 2 };

export function combine(results) {
  let best = { kind: "constant", source: "" };
  for (const r of results) {
    if (RANK[r.kind] > RANK[best.kind]) best = r;
  }
  return best;
}

export function findVariable(scope, name) {
  for (let s = scope; s; s = s.upper) {
    const v = s.set.get(name);
    if (v) return v;
  }
  return null;
}

function text(sourceCode, node) {
  return sourceCode.getText(node).replace(/\s+/g, "");
}

export function classify(node, context, scope, depth = 0) {
  const sc = context.sourceCode;
  if (!node || depth > MAX_DEPTH) return { kind: "unknown", source: "" };
  switch (node.type) {
    case "Literal":
      return { kind: "constant", source: "" };
    case "TemplateLiteral":
      return combine(node.expressions.map((e) => classify(e, context, scope, depth + 1)));
    case "BinaryExpression":
    case "LogicalExpression":
      return combine([classify(node.left, context, scope, depth + 1),
        classify(node.right, context, scope, depth + 1)]);
    case "ConditionalExpression":
      return combine([classify(node.consequent, context, scope, depth + 1),
        classify(node.alternate, context, scope, depth + 1)]);
    case "ArrayExpression":
      return combine(node.elements.filter(Boolean).map((e) => classify(e, context, scope, depth + 1)));
    case "AwaitExpression":
    case "TSAsExpression":
    case "TSNonNullExpression":
      return classify(node.argument ?? node.expression, context, scope, depth + 1);
    case "MemberExpression": {
      const t = text(sc, node);
      if (SOURCES.some((re) => re.test(t))) return { kind: "tainted", source: t };
      const obj = classify(node.object, context, scope, depth + 1);
      return obj.kind === "tainted" ? obj : { kind: "unknown", source: "" };
    }
    case "CallExpression": {
      const callee = text(sc, node.callee);
      if (SOURCE_CALLS.some((re) => re.test(callee))) return { kind: "tainted", source: `${callee}()` };
      if (SANITIZERS.has(callee)) return { kind: "constant", source: "" };
      const parts = node.arguments.map((a) => classify(a, context, scope, depth + 1));
      if (node.callee.type === "MemberExpression") {
        parts.push(classify(node.callee.object, context, scope, depth + 1));
      }
      const r = combine(parts);
      return r.kind === "tainted" ? r : { kind: "unknown", source: "" };
    }
    case "Identifier":
      return classifyIdentifier(node, context, scope, depth);
    default:
      return { kind: "unknown", source: "" };
  }
}

function classifyIdentifier(node, context, scope, depth) {
  const v = findVariable(scope, node.name);
  if (!v || v.defs.length === 0) return { kind: "unknown", source: "" };
  const results = [];
  for (const def of v.defs) {
    if (def.type === "Variable" && def.node.init) {
      const r = classify(def.node.init, context, scope, depth + 1);
      results.push(r.kind === "tainted" ? { ...r, source: `${node.name} (from ${r.source})` } : r);
    } else if (def.type === "Parameter") {
      results.push({ kind: "unknown", source: "" });
    } else {
      results.push({ kind: "unknown", source: "" });
    }
  }
  for (const ref of v.references) {
    if (ref.writeExpr && ref.writeExpr !== v.defs[0]?.node?.init) {
      results.push(classify(ref.writeExpr, context, scope, depth + 1));
    }
  }
  return combine(results);
}

// Does this identifier refer to require("mod") / import ... from "mod"?
export function bindsModule(identifier, scope, modules) {
  const v = findVariable(scope, identifier.name);
  if (!v) return false;
  return v.defs.some((def) => {
    if (def.type === "ImportBinding") {
      return modules.includes(def.parent?.source?.value);
    }
    if (def.type === "Variable" && def.node.init) {
      const init = def.node.init;
      return init.type === "CallExpression" && init.callee.type === "Identifier"
        && init.callee.name === "require" && modules.includes(init.arguments[0]?.value);
    }
    return false;
  });
}

// Enclosing function line range, for content hashing on the Python side.
export function scopeLines(node) {
  for (let n = node.parent; n; n = n.parent) {
    if (n.type.includes("Function")) return `${n.loc.start.line}-${n.loc.end.line}`;
  }
  return "";
}

export function report(context, node, verdict) {
  context.report({
    node,
    messageId: "hit",
    data: { kind: verdict.kind, source: verdict.source || "", scope: scopeLines(node) },
  });
}

// rce-sentinel ESLint plugin. Rule ids match config/rules/javascript.yaml so the Python
// side maps every hit to the same title, CWE, severity, attacker path, and fix.
// Messages are machine-readable: "kind=<constant|unknown|tainted>;source=<expr>;scope=<a-b>".

import { bindsModule, classify, report } from "./taint.mjs";

const CHILD_PROCESS = ["child_process", "node:child_process"];
const VM = ["vm", "node:vm"];
const SERIALIZE = ["node-serialize", "serialize-to-js"];
const meta = {
  type: "problem",
  schema: [],
  messages: { hit: "kind={{kind}};source={{source}};scope={{scope}}" },
};

function calleeParts(node) {
  const c = node.callee;
  if (c.type === "Identifier") return { object: null, name: c.name };
  if (c.type === "MemberExpression" && !c.computed && c.property.type === "Identifier") {
    return { object: c.object, name: c.property.name };
  }
  return { object: null, name: "" };
}

// Callee is <fn> from one of `modules`, as a bare import or as a member of the module object.
function fromModule(node, context, names, modules) {
  const { object, name } = calleeParts(node);
  if (!names.includes(name)) return false;
  const scope = context.sourceCode.getScope(node);
  if (object === null) return bindsModule(node.callee, scope, modules);
  if (object.type === "Identifier") return bindsModule(object, scope, modules);
  if (object.type === "CallExpression" && object.callee.name === "require") {
    return modules.includes(object.arguments[0]?.value);
  }
  return false;
}

function argRule(check, argIndex = 0, { skipConstant = true } = {}) {
  return {
    meta,
    create(context) {
      const visit = (node) => {
        if (!check(node, context)) return;
        const arg = node.arguments[argIndex];
        if (!arg) return;
        const verdict = classify(arg, context, context.sourceCode.getScope(node));
        if (skipConstant && verdict.kind === "constant") return;
        report(context, node, verdict);
      };
      return { CallExpression: visit, NewExpression: visit };
    },
  };
}

const isGlobal = (names) => (node) =>
  node.type === "CallExpression" && node.callee.type === "Identifier" && names.includes(node.callee.name);

const rules = {
  "js-eval": argRule((node) =>
    isGlobal(["eval"])(node)
    || (node.type === "CallExpression" && node.callee.type === "MemberExpression"
      && ["window", "globalThis", "global"].includes(node.callee.object.name)
      && node.callee.property.name === "eval")),

  "js-child-process-exec": argRule((node, ctx) =>
    node.type === "CallExpression" && fromModule(node, ctx, ["exec", "execSync"], CHILD_PROCESS)),

  "js-spawn-shell": {
    meta,
    create(context) {
      return {
        CallExpression(node) {
          if (!fromModule(node, context, ["spawn", "spawnSync", "execFile", "execFileSync"],
            CHILD_PROCESS)) return;
          const opts = node.arguments.find((a) => a.type === "ObjectExpression");
          const shell = opts?.properties.find((p) => p.key?.name === "shell");
          if (!shell || (shell.value.type === "Literal" && shell.value.value === false)) return;
          const scope = context.sourceCode.getScope(node);
          const args = node.arguments.filter((a) => a !== opts);
          const verdicts = args.map((a) => classify(a, context, scope));
          const tainted = verdicts.find((v) => v.kind === "tainted");
          report(context, node, tainted ?? { kind: "unknown", source: "" });
        },
      };
    },
  },

  "js-vm-run": argRule((node, ctx) =>
    (node.type === "CallExpression"
      && fromModule(node, ctx, ["runInNewContext", "runInThisContext", "runInContext",
        "compileFunction"], VM))
    || (node.type === "NewExpression" && node.callee.type === "MemberExpression"
      && node.callee.property.name === "Script"
      && bindsModule(node.callee.object, ctx.sourceCode.getScope(node), VM))),

  "js-string-timer": {
    meta,
    create(context) {
      return {
        CallExpression(node) {
          if (!isGlobal(["setTimeout", "setInterval"])(node)) return;
          const arg = node.arguments[0];
          if (!arg || !["Literal", "TemplateLiteral", "BinaryExpression"].includes(arg.type)) return;
          if (arg.type === "Literal" && typeof arg.value !== "string") return;
          report(context, node, classify(arg, context, context.sourceCode.getScope(node)));
        },
      };
    },
  },

  "js-node-serialize": argRule((node, ctx) =>
    node.type === "CallExpression" && fromModule(node, ctx, ["unserialize"], SERIALIZE),
  0, { skipConstant: false }),

  "js-dynamic-require": {
    meta,
    create(context) {
      const check = (node, arg) => {
        if (!arg) return;
        const verdict = classify(arg, context, context.sourceCode.getScope(node));
        if (verdict.kind !== "constant") report(context, node, verdict);
      };
      return {
        CallExpression(node) {
          if (isGlobal(["require"])(node)) check(node, node.arguments[0]);
        },
        ImportExpression(node) {
          check(node, node.source);
        },
      };
    },
  },
};

// new Function(a, b, body): every argument counts, so check them all.
rules["js-new-function"] = {
  meta,
  create(context) {
    const visit = (node) => {
      if (node.callee.type !== "Identifier" || node.callee.name !== "Function") return;
      const scope = context.sourceCode.getScope(node);
      const verdicts = node.arguments.map((a) => classify(a, context, scope));
      const worst = verdicts.find((v) => v.kind === "tainted")
        ?? verdicts.find((v) => v.kind === "unknown");
      if (worst) report(context, node, worst);
    };
    return { CallExpression: visit, NewExpression: visit };
  },
};

export default { meta: { name: "rce-sentinel", version: "0.1.0" }, rules };

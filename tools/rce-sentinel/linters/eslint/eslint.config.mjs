// Config used only by rce-sentinel. It is passed with -c, so a scanned repo's own
// ESLint config and plugins are never loaded.
import tsParser from "@typescript-eslint/parser";

import plugin from "./plugin/index.mjs";

const rules = Object.fromEntries(
  Object.keys(plugin.rules).map((id) => [`rce-sentinel/${id}`, "error"]),
);

export default [
  {
    files: ["**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs"],
    languageOptions: { ecmaVersion: "latest", sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "rce-sentinel": plugin },
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: "off" },
    rules,
  },
  {
    files: ["**/*.ts", "**/*.tsx", "**/*.mts", "**/*.cts"],
    languageOptions: { parser: tsParser, sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "rce-sentinel": plugin },
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: "off" },
    rules,
  },
];

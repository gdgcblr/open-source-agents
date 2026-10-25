import js from '@eslint/js';
import globals from 'globals';

export default [
  { ignores: ['node_modules/**', 'coverage/**', '.data/**'] },
  js.configs.recommended,
  {
    languageOptions: { ecmaVersion: 2023, sourceType: 'module', globals: { ...globals.node } },
    rules: {
      'no-console': ['error', { allow: ['error', 'warn'] }],
      'no-eval': 'error', 'no-implied-eval': 'error', 'no-new-func': 'error',
      'eqeqeq': ['error', 'always'], 'no-var': 'error', 'prefer-const': 'error',
    },
  },
  { files: ['scripts/**', 'test/**'], rules: { 'no-console': 'off' } },
];

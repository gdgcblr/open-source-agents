import js from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';

// The recommended JavaScript and TypeScript rules; formatting stays with the editor.
export default defineConfig(js.configs.recommended, tseslint.configs.recommended);

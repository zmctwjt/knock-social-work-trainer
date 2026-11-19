// ESLint 扁平配置（ESLint 9）
//
// 目标不是"零告警"，而是挡住几类真会出问题的写法：
// 1. 未使用变量 / 变量遮蔽 —— 常见于重构后漏删
// 2. React Hooks 依赖漏写 —— 会导致闭包读到旧值（本项目被它坑过：
//    load 回调依赖 loadDetail 但漏写，eslint 会直接报）
// 3. 非空断言与 any 滥用 —— 手工放宽到 warning，避免一次改动过载
//
// 刻意不开的规则：格式类（prettier 的事）、严格 a11y 全量（已有专门审查脚本）。
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'tests/**',          // 单元测试用 tsx 跑，语义不同
      'vite.config.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.es2021 },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // 逐步收紧：先当告警，避免一次改动几百处
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-non-null-assertion': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // 允许 console.warn/error（错误边界与降级都要用），禁止裸 console.log
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
);

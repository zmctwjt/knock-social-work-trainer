import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

/** 本地 AI 代理端口，与 server/.env 的 PORT 保持一致 */
const AI_PORT = process.env.PORT || '8787';

export default defineConfig({
  plugins: [react()],
  // 相对路径：dist 放到任意子目录都能正确加载静态资源
  base: './',
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    host: true, // 局域网可访问，方便手机测试
    proxy: {
      // 开发时把 /api 转给 server/index.mjs，前后端同源，无需处理 CORS
      '/api': {
        target: `http://127.0.0.1:${AI_PORT}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            // 内容资产单独成包：体量大且极少变动，便于长期缓存
            if (id.includes('/src/data/')) return 'data';
            return undefined;
          }
          // ECharts 单独成包：只有教师/管理页用到，学生端不必下载
          if (id.includes('echarts') || id.includes('zrender')) return 'charts';
          if (id.includes('react-router')) return 'router';
          if (id.includes('react') || id.includes('scheduler')) return 'react';
          return 'vendor';
        },
      },
    },
  },
});

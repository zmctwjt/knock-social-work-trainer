import React from 'react';
import ReactDOM from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App.tsx';
import './index.css';
import { bootstrapAi } from './lib/aiClient.ts';

// 启动时探测 AI 服务（同源 /api/health）。
// 探测失败不影响启动：全部判定自动回落到本地规则引擎。
bootstrapAi();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);

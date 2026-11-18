# 静态前端产物目录（Nginx / CDN 回源根目录）

构建产出（`npm run build` 的 `dist/`）在本目录展开，只保留：

```text
static/
├── index.html
├── assets/            # 带内容哈希的 JS/CSS
└── favicon.ico
```

约定：

1. 该目录内容由 CI 的 build 阶段产出镜像或对象存储桶同步，**不手工提交**；仓库中仅保留本说明与 `.gitkeep`。
2. `index.html` 必须 `Cache-Control: no-cache`，`assets/*` 为一年 `immutable`，因此发布 = 换 `index.html` + 新增哈希文件，旧文件保留 7 天再清理。
3. Compose 以只读方式挂载到 `/usr/share/nginx/html`；K8s 由独立的 `knock-web` Deployment 提供同一份产物。

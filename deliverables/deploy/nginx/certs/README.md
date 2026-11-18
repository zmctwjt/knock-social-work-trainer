# 证书目录（仅本地/单机自签用，生产由 cert-manager 或 ACME 自动签发）

本目录只放两个文件的软链或副本：

| 文件 | 内容 |
|---|---|
| `fullchain.pem` | 服务器证书 + 中间证书（顺序不可颠倒） |
| `privkey.pem` | 私钥（RSA 2048 或 ECDSA P-256） |

**生产禁止手工放置私钥**：K8s 由 cert-manager 写入 `knock-tls` Secret；单机可用 `certbot` 续期后由 systemd 钩子重载 Nginx。

本地自签（仅供 `docker compose` 冒烟，有效期 30 天）：

```bash
openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
  -keyout privkey.pem -out fullchain.pem \
  -subj "/C=CN/ST=Zhejiang/L=Hangzhou/O=Knock/CN=*.knock.example.com" \
  -addext "subjectAltName=DNS:api.knock.example.com,DNS:www.knock.example.com,DNS:admin.knock.example.com"
```

`.gitignore` 需忽略 `*.pem`；本目录仅保留本说明文件。

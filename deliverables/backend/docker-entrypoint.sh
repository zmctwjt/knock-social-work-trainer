#!/bin/sh
# 容器启动入口：先迁移，再起服务
#
# 为什么放在入口而不是单独的 migrate 服务：
# 试过用 compose 的 migrate 一次性服务 + service_completed_successfully
# 让 api 等它，但多轮实测里该服务连不上 mysql（Can't connect to MySQL
# server on 'mysql'），根因未定位，且会把失败留给编排层。
# 放入口脚本更简单：容器自己保证"库结构就绪才对外服务"，任何编排
# （compose / k8s / systemd）都不用额外记得先跑迁移。
#
# 幂等：alembic upgrade head 可以反复执行，已是最新时立即返回。
# 失败即退出非零，让容器进入重启/失败状态，而不是带病对外提供接口
# （空库会让所有查询 500，比启动失败更难排查）。
#
# RUN_MIGRATIONS=false 用于"迁移由外部统一执行"的场景：
# k8s 里是 migrate-job.yaml 先跑完再滚动 Deployment，若 3 个副本
# 各自再跑一次迁移会互相争抢（Alembic 默认没有分布式锁）。
set -e

if [ "${RUN_MIGRATIONS:-true}" = "false" ]; then
  echo "[entrypoint] RUN_MIGRATIONS=false，跳过迁移（由外部 Job 负责）"
else
  echo "[entrypoint] 执行数据库迁移…"
  alembic upgrade head
  echo "[entrypoint] 迁移完成"
fi

echo "[entrypoint] 启动服务"
exec "$@"

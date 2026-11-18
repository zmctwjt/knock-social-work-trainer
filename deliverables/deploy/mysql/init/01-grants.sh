#!/bin/sh
# MySQL 首次初始化（/docker-entrypoint-initdb.d）时执行：创建监控只读账号。
# 由官方 mysql:8.0 入口脚本调用（shell 执行），此时 root 口令已可用、MYSQL_* 环境变量已存在。
# 注意：只在数据目录为空时运行一次；已有数据卷不会重跑，账号丢失需手工重建（见 README）。
set -eu

EXPORTER_PASSWORD="${MYSQL_EXPORTER_PASSWORD:-exporter_pw}"

mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
-- mysqld-exporter 需要 PROCESS / REPLICATION CLIENT 才能读到 InnoDB 与复制状态，
-- 再加 SELECT 用于库表级指标；不给任何写权限。
CREATE USER IF NOT EXISTS 'exporter'@'%' IDENTIFIED WITH mysql_native_password BY '${EXPORTER_PASSWORD}';
ALTER USER 'exporter'@'%' IDENTIFIED WITH mysql_native_password BY '${EXPORTER_PASSWORD}';
GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'%';
FLUSH PRIVILEGES;
SQL

echo "exporter account ready"

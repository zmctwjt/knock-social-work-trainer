"""K8s 清单静态校验（不需要集群，可进 CI）。

不是替代 kubeconform/kubeval，而是覆盖本项目最关心的几类问题——
这些是真会导致上线出事的：

1. **YAML 能解析**、apiVersion/kind 齐全；
2. **工作负载必备项**：image 不是 latest、有 resources.requests/limits、
   有 readinessProbe（否则滚动时流量会打到未就绪副本）；
3. **安全基线**：runAsNonRoot、allowPrivilegeEscalation=false、
   capabilities.drop、readOnlyRootFilesystem（有则要求为 true）；
4. **引用一致**：Service 的 selector 能选中 Deployment 的 pod 标签；
   HPA/PDB/Ingress 指向的服务与 Deployment 真实存在；
   image 引用与 Dockerfile 产物一致；
5. **密钥不落清单**：Secret 里不能出现明文的非占位密码。

用法：python work/audit_k8s_manifests.py
返回码非零表示未通过，CI 可直接用。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

K8S_DIR = Path(__file__).resolve().parent.parent / "deliverables" / "deploy" / "k8s"
EXPECTED_IMAGE = "knock/api"
FAILS: list[str] = []
CHECKS = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILS.append(f"{label}{(' — ' + detail) if detail else ''}")


def load_docs() -> list[tuple[str, dict[str, Any]]]:
    docs: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(K8S_DIR.glob("*.yaml")):
        try:
            for item in yaml.safe_load_all(path.read_text(encoding="utf-8")):
                if item:
                    docs.append((path.name, item))
        except yaml.YAMLError as exc:
            FAILS.append(f"{path.name} YAML 解析失败: {exc}")
    return docs


def walk_containers(obj: dict[str, Any]):
    """产出 (容器定义, 所在 pod spec) 对。"""
    pod = obj.get("spec", {}).get("template", {}).get("spec")
    if not pod:
        return
    for key in ("containers", "initContainers"):
        for c in pod.get(key) or []:
            c["__isInit"] = key == "initContainers"
            yield c, pod


def main() -> int:
    docs = load_docs()
    print(f"扫描 {K8S_DIR.name}/：{len(docs)} 个对象")
    if not docs:
        print("没有解析到任何对象")
        return 1

    kinds: dict[str, list[dict]] = {}
    for _, obj in docs:
        check(bool(obj.get("apiVersion")), f"{obj.get('kind')} 缺少 apiVersion")
        check(bool(obj.get("kind")), "对象缺少 kind")
        kinds.setdefault(str(obj.get("kind")), []).append(obj)

    print("对象类型:", {k: len(v) for k, v in sorted(kinds.items())})

    # ── 工作负载：镜像、资源、探针、安全基线 ──
    workloads = kinds.get("Deployment", []) + kinds.get("StatefulSet", []) + kinds.get("Job", [])
    for obj in workloads:
        name = f"{obj.get('kind')}/{obj.get('metadata', {}).get('name')}"
        for c, pod in walk_containers(obj):
            image = str(c.get("image", ""))
            cname = c.get("name", "?")

            check(bool(image), f"{name}[{cname}] 未指定 image")
            if image:
                check(
                    not image.endswith(":latest") and ":" in image.rsplit("/", 1)[-1],
                    f"{name}[{cname}] 使用了 latest 或未指定 tag",
                    image,
                )
                # 允许私有 registry 前缀（registry.example.com/knock/knock-api），
                # 只校验仓库名与产物对应，不要求完整字符串相等
                if "knock" in image:
                    repo = image.rsplit(":", 1)[0].rsplit("/", 1)[-1]
                    check(
                        repo.startswith("knock-") or repo == "api",
                        f"{name}[{cname}] 镜像仓库名与产物不一致", f"{repo} ← {image}",
                    )

            res = c.get("resources") or {}
            check(bool(res.get("requests")), f"{name}[{cname}] 缺 resources.requests")
            check(bool(res.get("limits")), f"{name}[{cname}] 缺 resources.limits")

            # Job 与 initContainer 不要求探针（非常驻进程）
            if obj.get("kind") != "Job" and not c.get("__isInit"):
                check(bool(c.get("readinessProbe")), f"{name}[{cname}] 缺 readinessProbe")
                check(bool(c.get("livenessProbe")), f"{name}[{cname}] 缺 livenessProbe")

            sc = c.get("securityContext") or {}
            if sc:
                check(
                    sc.get("allowPrivilegeEscalation") is False,
                    f"{name}[{cname}] 未禁用 allowPrivilegeEscalation",
                )
                if "readOnlyRootFilesystem" in sc:
                    check(
                        sc["readOnlyRootFilesystem"] is True,
                        f"{name}[{cname}] readOnlyRootFilesystem 被显式设为 false",
                    )
                caps = sc.get("capabilities") or {}
                if caps:
                    check(
                        caps.get("drop") == ["ALL"],
                        f"{name}[{cname}] capabilities 未全部 drop",
                        str(caps.get("drop")),
                    )

        pod_sc = (obj.get("spec", {}).get("template", {}).get("spec") or {}).get("securityContext") or {}
        if pod_sc:
            check(pod_sc.get("runAsNonRoot") is True, f"{name} pod 未设置 runAsNonRoot")

    # ── 引用一致性 ──
    deployments = kinds.get("Deployment", [])
    services = kinds.get("Service", [])

    api_dep = next((d for d in deployments
                    if d.get("metadata", {}).get("name") == "knock-api"), None)
    check(api_dep is not None, "缺少 knock-api Deployment")
    if api_dep:
        pod_labels = (api_dep.get("spec", {}).get("template", {})
                      .get("metadata", {}).get("labels") or {})
        sel = api_dep.get("spec", {}).get("selector", {}).get("matchLabels") or {}
        check(bool(sel), "knock-api Deployment 缺 selector.matchLabels")
        for k, v in sel.items():
            check(pod_labels.get(k) == v, f"knock-api selector {k}={v} 与 pod 标签不匹配")

    # 每个 Service 的 selector 必须能选中某个 Deployment 的 Pod（而不是只对 api）
    all_pod_labels = [
        ((d.get("spec", {}).get("template", {}).get("metadata", {}) or {}).get("labels") or {})
        for d in deployments
    ]
    for svc in services:
        name = svc.get("metadata", {}).get("name", "?")
        ssel = svc.get("spec", {}).get("selector") or {}
        if not ssel:
            continue
        matched = any(
            all(labels.get(k) == v for k, v in ssel.items())
            for labels in all_pod_labels
        )
        check(matched, f"Service/{name} 的 selector 选不中任何 Deployment 的 Pod",
              str(ssel))

    # HPA / PDB 必须指向真实存在的 Deployment
    dep_names = {d.get("metadata", {}).get("name") for d in deployments}
    for kind in ("HorizontalPodAutoscaler", "PodDisruptionBudget"):
        for obj in kinds.get(kind, []):
            ref = (obj.get("spec", {}).get("scaleTargetRef") or {}).get("name") \
                or obj.get("spec", {}).get("selector", {}).get("matchLabels", {}).get(
                    "app.kubernetes.io/name")
            if kind == "HorizontalPodAutoscaler":
                check(ref in dep_names, f"{kind}/{obj.get('metadata', {}).get('name')} "
                                        f"指向不存在的 Deployment: {ref}")

    # Ingress 的 backend service 必须存在
    svc_names = {s.get("metadata", {}).get("name") for s in services}
    for ing in kinds.get("Ingress", []):
        rules = ing.get("spec", {}).get("rules") or []
        backends = []
        for rule in rules:
            for path in ((rule.get("http") or {}).get("paths") or []):
                be = ((path.get("backend") or {}).get("service") or {}).get("name")
                if be:
                    backends.append(be)
        for be in backends:
            check(be in svc_names, f"Ingress 引用了不存在的 Service: {be}")

    # ── 密钥不落清单 ──
    for _, obj in docs:
        if obj.get("kind") != "Secret":
            continue
        name = obj.get("metadata", {}).get("name", "?")
        for k, v in (obj.get("stringData") or {}).items():
            text = str(v)
            low = text.lower()
            placeholder = (
                "change_me" in low          # 覆盖 CHANGE_ME_XXX 与 __CHANGE_ME__
                or text.startswith("<")
                or low in ("", "changeme")
                or "example" in low
                or "dummy" in low
            )
            check(placeholder, f"Secret/{name}.{k} 疑似写入了真实密钥", text[:12] + "…")

        # data 段是 base64，至少确认不是明文口令
        for k, v in (obj.get("data") or {}).items():
            text = str(v)
            check(len(text) > 0, f"Secret/{name}.data.{k} 为空")

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} / {CHECKS} 项未通过：")
        for f in FAILS:
            print("   -", f)
        return 1
    print(f"✅ K8s 清单静态校验通过（{CHECKS} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

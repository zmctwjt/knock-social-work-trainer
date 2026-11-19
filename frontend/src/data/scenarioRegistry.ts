/**
 * 服务端案例注册表
 *
 * 背景：教师/管理员可以在「案例管理」里新建服务对象，案例存在数据库。
 * 但前端有一批**同步**调用（路由守卫 `isKnownScenario`、训练页与复盘页
 * 取角色信息的 `getScenario`）是基于内置静态数据的，同步函数没法等接口。
 *
 * 做法：进入应用时把服务端案例拉一次放进模块级缓存，之后同步查表。
 * 这样既保留了同步调用的简单性，又让教师新建的角色能被完整使用
 * （否则会出现"选角页看得到、点进去被路由守卫拦下"）。
 *
 * 缓存不可用时（接口挂了）自然回落静态内置案例——与知识库、
 * 判定词表同一套降级思路。
 */

export interface ServerScenario {
  id: string;
  name: string;
  age: number;
  gender: string;
  archetype: string;
  difficulty: number;
  sensitive_tag: string | null;
  brief: string;
  custom: boolean;
}

const REGISTRY = new Map<string, ServerScenario>();

/** 把接口返回的案例写入缓存（可重复调用，后来者覆盖）。 */
export function hydrateScenarios(list: ServerScenario[]): void {
  for (const item of list) {
    if (item?.id) REGISTRY.set(item.id, item);
  }
}

/** 同步取一个服务端案例。没拉过或不存在返回 undefined。 */
export function lookupScenario(id: string): ServerScenario | undefined {
  return REGISTRY.get(id);
}

/** 是否为服务端已知案例（含内置与教师自建）。 */
export function isServerScenario(id: string): boolean {
  return REGISTRY.has(id);
}

/** 当前缓存里的全部案例（调试与测试用）。 */
export function listServerScenarios(): ServerScenario[] {
  return [...REGISTRY.values()];
}

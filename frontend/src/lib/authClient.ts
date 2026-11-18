/**
 * 叩门 · 账号与鉴权客户端
 *
 * 与 `aiClient.ts` 的分工：这里只管身份（登录/登出/令牌/当前账号），
 * AI 链路仍走 aiClient。两者都同源请求后端，不直连外部服务。
 *
 * 三条设计约束：
 *   1. 令牌存 localStorage，但**权限以服务端为准**——前端读到的 role 只用于
 *      决定显示什么入口，真正的拦截在服务端 `require_roles`；
 *   2. 401 统一清理登录态并抛出，由调用方决定是否跳登录页；
 *   3. 无后端时（旧静态演示模式）降级为本地账号，保证页面不白屏。
 */

const API_BASE = (import.meta.env?.VITE_API_BASE as string | undefined) || '';
const K_TOKEN = 'knock.auth.access';
const K_REFRESH = 'knock.auth.refresh';
const K_USER = 'knock.auth.user';
const K_MODE = 'knock.auth.mode'; // 'server' | 'local'

/** 默认请求超时。AI 类接口在服务端自带 45s 预算，这里留 60s 兜底。 */
const DEFAULT_TIMEOUT_MS = 60_000;

export type Role = 'student' | 'teacher' | 'admin' | 'guest';

export interface AuthUser {
  id: string;
  username: string;
  nickname: string;
  role: Role;
  is_guest: boolean;
}

export interface AuthResult {
  ok: boolean;
  msg: string;
  user?: AuthUser;
}

/** 后端是否可用（决定走真实账号还是本地降级）。null 表示尚未探测。 */
let serverMode: boolean | null = null;

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function currentUser(): AuthUser | null {
  return readJson<AuthUser | null>(K_USER, null);
}

export function accessToken(): string {
  return localStorage.getItem(K_TOKEN) || '';
}

export function isServerMode(): boolean {
  return serverMode === true;
}

function saveSession(user: AuthUser, tokens: { access_token: string; refresh_token: string }): void {
  localStorage.setItem(K_USER, JSON.stringify(user));
  localStorage.setItem(K_TOKEN, tokens.access_token);
  localStorage.setItem(K_REFRESH, tokens.refresh_token);
  localStorage.setItem(K_MODE, 'server');
  serverMode = true;
}

export function clearSession(): void {
  localStorage.removeItem(K_USER);
  localStorage.removeItem(K_TOKEN);
  localStorage.removeItem(K_REFRESH);
}

/** 角色中文名，用于顶栏与账号菜单。 */
export const ROLE_LABEL: Record<Role, string> = {
  student: '学生',
  teacher: '教师',
  admin: '管理员',
  guest: '访客',
};

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<{ ok: boolean; status: number; body?: T; msg?: string }> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = accessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  // 超时控制：没有它时后端无响应会让页面一直转圈，用户只能刷新。
  // 用 AbortController 而不是 Promise.race —— 前者能真正取消底层请求。
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    const text = await resp.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = null;
    }
    const envelope = body as
      | { code?: number; message?: string; data?: T }
      | null;
    if (!resp.ok || (envelope && envelope.code !== 0)) {
      return {
        ok: false,
        status: resp.status,
        msg: envelope?.message || `HTTP ${resp.status}`,
      };
    }
    return { ok: true, status: resp.status, body: envelope?.data as T };
  } catch (err) {
    // AbortError 表示超时被主动取消，与"网络不可达"是两类问题
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { ok: false, status: 0, msg: '请求超时，请稍后重试' };
    }
    return { ok: false, status: 0, msg: err instanceof Error ? err.message : '网络错误' };
  } finally {
    clearTimeout(timer);
  }
}

/** 探测后端账号服务是否可用；失败不抛错，交给调用方降级。 */
export async function probeServer(): Promise<boolean> {
  if (serverMode !== null) return serverMode;
  const r = await request<{ ok: boolean }>('/api/v1/auth/me');
  // 401 说明服务在但未登录，同样算"服务可用"
  serverMode = r.status === 401 || r.ok;
  return serverMode;
}

export async function login(username: string, password: string): Promise<AuthResult> {
  const r = await request<{ account: AuthUser; tokens: { access_token: string; refresh_token: string } }>(
    '/api/v1/auth/login',
    { method: 'POST', body: JSON.stringify({ username: username.trim().toLowerCase(), password }) },
  );
  if (!r.ok || !r.body) {
    return { ok: false, msg: r.status === 403 ? '账号已被停用，请联系管理员' : r.msg || '登录失败' };
  }
  saveSession(r.body.account, r.body.tokens);
  return { ok: true, msg: `登录成功，当前角色：${ROLE_LABEL[r.body.account.role]}`, user: r.body.account };
}

/** 游客只读体验。 */
export async function loginAsGuest(nickname = '访客'): Promise<AuthResult> {
  const r = await request<{ account: AuthUser; tokens: { access_token: string; refresh_token: string } }>(
    '/api/v1/auth/guest',
    { method: 'POST', body: JSON.stringify({ nickname }) },
  );
  if (!r.ok || !r.body) return { ok: false, msg: r.msg || '访客登录失败' };
  saveSession(r.body.account, r.body.tokens);
  return { ok: true, msg: '已进入访客模式（只读）', user: r.body.account };
}

export async function logout(): Promise<void> {
  try {
    await request('/api/v1/auth/logout', { method: 'POST' });
  } catch {
    /* 后端不可达也要清本地态 */
  }
  clearSession();
}

/** 刷新令牌。页面长时间停留后调用，失败即视为掉线。 */
export async function refresh(): Promise<boolean> {
  const token = localStorage.getItem(K_REFRESH) || '';
  if (!token) return false;
  const r = await request<{ access_token: string; refresh_token: string }>(
    '/api/v1/auth/refresh',
    { method: 'POST', body: JSON.stringify({ refresh_token: token }) },
  );
  if (!r.ok || !r.body) {
    clearSession();
    return false;
  }
  localStorage.setItem(K_TOKEN, r.body.access_token);
  localStorage.setItem(K_REFRESH, r.body.refresh_token);
  return true;
}

/** 带鉴权的 GET/POST 封装，供教师端与管理端页面复用。 */
/** 接口失败的结构化错误，供页面区分"没数据"与"请求失败"。 */
export interface ApiError {
  status: number;
  message: string;
  /** 401 已清理登录态，调用方应跳登录页 */
  unauthorized: boolean;
  /** 403 越权：页面应提示"无权限"而不是"加载失败" */
  forbidden: boolean;
  /** 网络不可达（后端没起 / 断网） */
  offline: boolean;
}

export interface ApiResult<T> {
  ok: boolean;
  data: T | null;
  error: ApiError | null;
}

function toApiError(r: { status: number; msg?: string }): ApiError {
  return {
    status: r.status,
    message: r.msg || `请求失败（HTTP ${r.status}）`,
    unauthorized: r.status === 401,
    forbidden: r.status === 403,
    offline: r.status === 0,
  };
}

/**
 * 带错误信息的 GET。
 *
 * 相比直接返回 null，调用方现在能区分三种情况：
 * 成功但无数据（data 有值为空数组）、无权限（403）、网络失败（offline）。
 * 这三种在界面上应给不同提示，否则用户看到"暂无数据"会以为是系统坏了。
 */
export async function apiGetResult<T>(path: string): Promise<ApiResult<T>> {
  const r = await request<T>(path);
  if (!r.ok && r.status === 401) clearSession();
  if (r.ok) return { ok: true, data: r.body as T, error: null };
  return { ok: false, data: null, error: toApiError(r) };
}

/** 兼容旧调用：只关心数据，失败返回 null。新代码建议用 apiGetResult。 */
export async function apiGet<T>(path: string): Promise<T | null> {
  const r = await apiGetResult<T>(path);
  return r.data;
}

/** 把 ApiError 转成给用户看的文案，避免各处重复写判断。 */
export function describeApiError(err: ApiError | null, fallback = '加载失败'): string {
  if (!err) return fallback;
  if (err.offline) return '无法连接服务器，请确认后端已启动';
  if (err.unauthorized) return '登录已过期，请重新登录';
  if (err.forbidden) return '当前角色无权查看这部分数据';
  if (err.status >= 500) return '服务端异常，请稍后重试或联系管理员';
  return err.message || fallback;
}

export async function apiSend<T>(
  method: 'POST' | 'PATCH' | 'DELETE',
  path: string,
  payload?: unknown,
): Promise<{ ok: boolean; msg: string; data?: T }> {
  const r = await request<T>(path, {
    method,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!r.ok && r.status === 401) clearSession();
  return { ok: r.ok, msg: r.ok ? 'ok' : r.msg || '操作失败', data: r.body };
}

/** 角色登录后的默认落地页：各自进入自己的工作台，而不是统一进学生首页。 */
export function homeFor(role: Role): string {
  if (role === 'admin') return '/admin';
  if (role === 'teacher') return '/teacher';
  return '/';
}

/** 该角色可见的导航分区：避免学生看到管理入口、教师看到账号管理。 */
export function navItemsFor(role: Role): { to: string; no: string; label: string }[] {
  const studentNav = [
    { to: '/', no: '01', label: '首页' },
    { to: '/cases', no: '02', label: '服务对象' },
    { to: '/training', no: '03', label: '面谈训练' },
    { to: '/settle', no: '04', label: '阶段结算' },
    { to: '/review', no: '05', label: '复盘报告' },
    { to: '/growth', no: '06', label: '成长中心' },
    { to: '/knowledge', no: '07', label: '知识库' },
    { to: '/about', no: '08', label: '关于与声明' },
    { to: '/settings', no: '09', label: '设置' },
  ];
  const teacherNav = [
    { to: '/teacher', no: '01', label: '班级看板' },
    { to: '/knowledge', no: '02', label: '知识库' },
    { to: '/about', no: '03', label: '关于与声明' },
    { to: '/settings', no: '04', label: '设置' },
  ];
  const adminNav = [
    { to: '/admin', no: '01', label: '管理后台' },
    { to: '/teacher', no: '02', label: '班级看板' },
    { to: '/knowledge', no: '03', label: '知识库' },
    { to: '/about', no: '04', label: '关于与声明' },
    { to: '/settings', no: '05', label: '设置' },
  ];
  if (role === 'admin') return adminNav;
  if (role === 'teacher') return teacherNav;
  if (role === 'guest') {
    // 访客只读：不给训练相关入口
    return [
      { to: '/', no: '01', label: '首页' },
      { to: '/cases', no: '02', label: '服务对象' },
      { to: '/knowledge', no: '03', label: '知识库' },
      { to: '/about', no: '04', label: '关于与声明' },
    ];
  }
  return studentNav;
}

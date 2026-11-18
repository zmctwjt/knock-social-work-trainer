/**
 * 全局状态：账号 + 当前训练会话 + 历史记录
 *
 * 设计说明：
 * - 本地实现（localStorage），零后端也能完整演示账号体系
 * - 接口与 Supabase Auth 对齐，接入时只换实现不改调用方
 * - 训练结果写入当前账号的历史，供成长中心/热力图使用
 */
import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import type { DimensionKey, MarginNote, ChatMessage } from '../types.ts';
import * as auth from '../lib/authClient.ts';
import type { Role } from '../lib/authClient.ts';

export interface Account {
  /** 服务端账号才有：用户名与角色；纯本地演示账号为 undefined */
  username?: string;
  role?: Role;
  id: string;
  nickname: string;
  /** 仅本地演示用；接 Supabase Auth 后移除 */
  passHash: string;
  createdAt: number;
}

export interface TrainingRecord {
  id: string;
  nickname: string;
  scriptId: string;
  scriptName: string;
  archetype: string;
  difficulty: string;
  blindfold: boolean;
  uiPhase: number;
  scores: Record<DimensionKey, number>;
  total: number;
  aiUsed: boolean;
  durationSec: number;
  /** ★ 逐句点评 —— 详情弹窗要用 */
  notes: MarginNote[];
  /** 当时的完整对话 */
  transcript: { role: 'worker' | 'client'; text: string }[];
  createdAt: number;
}

export interface CurrentSession {
  scriptId: string;
  difficulty: string;
  blindfold: boolean;
  emotion: number;
  turn: number;
  phase: 1 | 2 | 3;
  judgeCount: number;
  hopelessSeen: boolean;
  /** ★ 完整对话记录 —— 存进 store 才能跨页面保留 */
  messages: ChatMessage[];
  notes: MarginNote[];
  /** 已提交过的阶段数（提交后不丢历史，只清当前对话） */
  submittedPhases: number[];
  adjust: Record<DimensionKey, number>;
  /** 供结算 / 复盘页读 */
  lastResult: {
    scores: Record<DimensionKey, number>;
    total: number;
    weakDim: DimensionKey;
    weakScore: number;
  } | null;
}

/** 登录结果：带上角色，调用方据此决定落地页，不必再读 localStorage。 */
export interface AuthOutcome {
  ok: boolean;
  msg: string;
  role?: Role;
}

interface Store {
  /* 账号 */
  account: Account | null;
  accounts: Account[];
  /** 服务端账号模式：true 表示连的是后端真实账号，false 为纯本地演示 */
  serverMode: boolean;
  role: Role;
  register: (nickname: string, password: string) => Promise<AuthOutcome>;
  login: (nickname: string, password: string) => Promise<AuthOutcome>;
  loginGuest: () => Promise<AuthOutcome>;
  logout: () => void;
  switchAccount: (id: string) => void;

  /* 当前训练 */
  session: CurrentSession | null;
  startSession: (scriptId: string, difficulty: string) => void;
  patchSession: (p: Partial<CurrentSession>) => void;
  endSession: () => void;

  /* 历史 */
  records: TrainingRecord[];
  addRecord: (r: Omit<TrainingRecord, 'id' | 'createdAt' | 'nickname'>) => TrainingRecord | null;

  /* 引导 */
  tourDone: boolean;
  setTourDone: (v: boolean) => void;
}

const Ctx = createContext<Store | null>(null);

/* 简易哈希（仅本地演示，不能用于生产） */
function hash(s: string): string {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return 'h' + h.toString(36);
}

const K_ACC = 'knock.accounts';
const K_CUR = 'knock.currentAccount';
const K_REC = 'knock.records';
/** 会话按账号分槽存放：knock.session.<accountId> */
const K_SESSION = 'knock.session.';

/** 从设置读「默认开启无剧透模式」 */
function readBlindfold(): boolean {
  try {
    const raw = localStorage.getItem('knock.settings');
    return raw ? (JSON.parse(raw).blindfold_default ?? true) : true;
  } catch {
    return true;
  }
}

function load<T>(k: string, d: T): T {
  try {
    const v = localStorage.getItem(k);
    return v ? (JSON.parse(v) as T) : d;
  } catch {
    return d;
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [accounts, setAccounts] = useState<Account[]>(() => load<Account[]>(K_ACC, []));
  /* ★ 账号恢复必须用惰性初始化，不能放 useEffect：
     Guard 的 nav('/login') 写在子组件 effect 里，React 先跑子组件 effect，
     再跑 Provider 的 effect —— 已登录用户刷新 /growth 会被先踢回登录页。 */
  const [account, setAccount] = useState<Account | null>(() => {
    const id = localStorage.getItem(K_CUR);
    if (!id) return null;
    return load<Account[]>(K_ACC, []).find((a) => a.id === id) ?? null;
  });
  /* ★ 会话同步惰性读回：F5 后接着上次的对话，而不是从空白开始 */
  const [session, setSession] = useState<CurrentSession | null>(() =>
    account ? load<CurrentSession | null>(K_SESSION + account.id, null) : null,
  );
  const [records, setRecords] = useState<TrainingRecord[]>(() => load<TrainingRecord[]>(K_REC, []));
  const [tourDone, setTourDone] = useState<boolean>(
    () => localStorage.getItem('knock.tourDone') === '1',
  );

  useEffect(() => { localStorage.setItem(K_ACC, JSON.stringify(accounts)); }, [accounts]);
  useEffect(() => { localStorage.setItem(K_REC, JSON.stringify(records)); }, [records]);

  /* ★ 会话持久化：800ms 节流写当前账号自己的槽位。
     session 为空（提交完 / 退出 / 切换账号）时清掉槽位，避免 F5 后复活旧对话。 */
  useEffect(() => {
    if (!account) return;
    const key = K_SESSION + account.id;
    const t = setTimeout(() => {
      try {
        if (session) localStorage.setItem(key, JSON.stringify(session));
        else localStorage.removeItem(key);
      } catch { /* 配额满时放弃持久化，不影响本次训练 */ }
    }, 800);
    return () => clearTimeout(t);
  }, [session, account]);

  /* ── 账号：优先走后端真实账号，后端不可用时回落到本地演示账号 ──
     这样"单机双击 start.bat"与"接后端跑"两种形态都能用，
     但只要有后端，角色就由服务端签发，前端只负责显示。 */
  const toAccount = (user: auth.AuthUser): Account => ({
    id: user.id,
    nickname: user.nickname,
    passHash: '',
    createdAt: Date.now(),
    username: user.username,
    role: user.role,
  });

  /* 启动后探测一次后端账号服务：成功即进入"真实角色"模式 */
  const [serverMode, setServerMode] = useState<boolean>(auth.isServerMode());
  useEffect(() => {
    let alive = true;
    void auth.probeServer().then((ok) => {
      if (alive) setServerMode(ok);
    });
    return () => {
      alive = false;
    };
  }, []);

  /** 当前角色：服务端账号以服务端签发为准；本地演示账号一律按学生处理 */
  const role: Role = account?.role ?? 'student';

  const register = useCallback(async (nickname: string, password: string) => {
    const n = nickname.trim();
    if (n.length < 1) return { ok: false, msg: '账号不能为空' };
    if (password.length < 6) return { ok: false, msg: '密码至少 6 位' };

    // 服务端不开放自助注册（教务统一导入），这里走登录并给出明确提示
    if (await auth.probeServer()) {
      const r = await auth.login(n, password);
      if (!r.ok) {
        return { ok: false, msg: `${r.msg}（账号由教务统一创建，请联系管理员）` };
      }
      const a = toAccount(r.user!);
      setAccounts((x) => [...x.filter((y) => y.id !== a.id), a]);
      setAccount(a);
      localStorage.setItem(K_CUR, a.id);
      return { ok: true, msg: r.msg, role: a.role };
    }

    // 无后端：退回本地演示账号
    if (accounts.some((a) => a.nickname === n)) return { ok: false, msg: '该昵称已被注册' };
    const a: Account = {
      id: 'u' + Date.now().toString(36),
      nickname: n,
      passHash: hash(password),
      createdAt: Date.now(),
    };
    setAccounts((x) => [...x, a]);
    setAccount(a);
    localStorage.setItem(K_CUR, a.id);
    return { ok: true, msg: '注册成功（本地演示账号）', role: 'student' };
  }, [accounts]);

  const login = useCallback(async (nickname: string, password: string) => {
    const n = nickname.trim();
    if (!n) return { ok: false, msg: '账号不能为空' };

    if (await auth.probeServer()) {
      const r = await auth.login(n, password);
      if (!r.ok) return { ok: false, msg: r.msg };
      const a = toAccount(r.user!);
      setAccounts((x) => [...x.filter((y) => y.id !== a.id), a]);
      setAccount(a);
      localStorage.setItem(K_CUR, a.id);
      return { ok: true, msg: r.msg, role: a.role };
    }

    const a = accounts.find((x) => x.nickname === n);
    if (!a) return { ok: false, msg: '该昵称尚未注册' };
    if (a.passHash !== hash(password)) return { ok: false, msg: '密码错误' };
    setAccount(a);
    localStorage.setItem(K_CUR, a.id);
    return { ok: true, msg: '登录成功（本地演示账号）', role: 'student' };
  }, [accounts]);

  const loginGuest = useCallback(async () => {
    if (!(await auth.probeServer())) {
      return { ok: false, msg: '后端未启动，访客模式不可用' };
    }
    const r = await auth.loginAsGuest();
    if (!r.ok) return { ok: false, msg: r.msg };
    const a = toAccount(r.user!);
    setAccount(a);
    localStorage.setItem(K_CUR, a.id);
    return { ok: true, msg: r.msg, role: a.role };
  }, []);

  const logout = useCallback(() => {
    void auth.logout();
    setAccount(null);
    setSession(null);
    localStorage.removeItem(K_CUR);
  }, []);

  const switchAccount = useCallback((id: string) => {
    const a = accounts.find((x) => x.id === id);
    if (a) {
      setAccount(a);
      setSession(null);
      localStorage.setItem(K_CUR, a.id);
    }
  }, [accounts]);

  const startSession = useCallback((scriptId: string, difficulty: string) => {
    setSession({
      scriptId, difficulty, blindfold: readBlindfold(), emotion: 45, turn: 1, phase: 1,
      judgeCount: 0, hopelessSeen: false, messages: [], notes: [],
      submittedPhases: [], lastResult: null,
      adjust: { empathy: 0, question: 0, advice: 0, ethics: 0, process: 0, risk: 0 },
    });
  }, []);

  const patchSession = useCallback((p: Partial<CurrentSession>) => {
    setSession((s) => {
      if (s) return { ...s, ...p };
      // session 为空时不要静默丢弃 —— 用 patch 里的 scriptId 补建一条
      if (!p.scriptId) {
        console.error('[叩门] patchSession 时 session 为空，且 patch 里没有 scriptId');
        return s;
      }
      return {
        scriptId: p.scriptId, difficulty: p.difficulty ?? '标准实训',
        blindfold: false, emotion: 45, turn: 1, phase: 1,
        judgeCount: 0, hopelessSeen: false,
        messages: [], notes: [], submittedPhases: [], lastResult: null,
        adjust: { empathy: 0, question: 0, advice: 0, ethics: 0, process: 0, risk: 0 },
        ...p,
      };
    });
  }, []);

  const endSession = useCallback(() => setSession(null), []);

  const addRecord = useCallback((r: Omit<TrainingRecord, 'id' | 'createdAt' | 'nickname'>) => {
    if (!account) return null;
    const rec: TrainingRecord = {
      ...r,
      id: 'r' + Date.now().toString(36),
      nickname: account.nickname,
      createdAt: Date.now(),
    };
    setRecords((x) => [rec, ...x]);
    return rec;
  }, [account]);

  const markTour = useCallback((v: boolean) => {
    setTourDone(v);
    localStorage.setItem('knock.tourDone', v ? '1' : '0');
  }, []);

  return (
    <Ctx.Provider value={{
      account, accounts, serverMode, role, register, login, loginGuest, logout, switchAccount,
      session, startSession, patchSession, endSession,
      records, addRecord,
      tourDone, setTourDone: markTour,
    }}>
      {children}
    </Ctx.Provider>
  );
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error('useStore 必须在 StoreProvider 内使用');
  return s;
}

/** 当前账号的训练记录 */
export function useMyRecords(): TrainingRecord[] {
  const { records, account } = useStore();
  return account ? records.filter((r) => r.nickname === account.nickname) : [];
}

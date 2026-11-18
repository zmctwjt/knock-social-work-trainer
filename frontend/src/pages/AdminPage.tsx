/**
 * 管理后台
 *
 * 六个视图：运行概览 / 账号管理 / 平台趋势 / 内容维护 / 词表维护 / 台词节点。
 * 权限在服务端（`require_roles(admin)`），本页只决定"看到什么入口"；
 * 非管理员访问时所有接口返回 40301，页面会切到无权限态。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import { apiGet, apiGetResult, apiSend, describeApiError } from '../lib/authClient.ts';
import {
  AverageTrendChart,
  DimensionBarChart,
  DistributionPieChart,
  ScenarioUsageChart,
} from '../components/charts.tsx';

interface Overview {
  accounts: number;
  teachers: number;
  sessions: number;
  records: number;
  ai_calls_24h: number;
  ai_configured: boolean;
  model_chain: string[];
  daily_cap: number;
  environment: string;
}

interface AccountRow {
  id: string;
  username: string;
  nickname: string;
  role: string;
  is_active: boolean;
  is_guest: boolean;
  last_login_at: string | null;
}

interface DimAvg { key: string; name: string; avg: number; count: number }
interface TrendPoint { date: string; sessions: number; avg_total: number }
interface ScenarioUsage {
  scenario_id: string; scenario_name: string; sessions: number; avg_total: number;
}
interface AdminTrend {
  days: number;
  points: TrendPoint[];
  role_distribution: Record<string, number>;
  scenario_usage: ScenarioUsage[];
  dimensions: DimAvg[];
}

interface RuleGroup {
  group: string; label: string; baseline: number; effective: number; protected: boolean;
}
interface CustomWord {
  id: string; group: string; group_label: string; word: string; enabled: boolean; note: string;
}

interface ScriptLine {
  id: string; scenario_id: string | null; emotion_bucket: string;
  bucket_label: string; text: string; active: boolean;
}

interface ScenarioRow {
  id: string; name: string; age: number; gender: string; archetype: string;
  difficulty: number; difficulty_label: string; active: boolean;
}

interface CardRow {
  id: string; title: string; category: string; summary: string;
}

interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

interface AiLog {
  id: string; purpose: string; status: string; model: string;
  latency_ms: number; degrade_reason: string | null; used_ai: boolean;
  cache_hit: boolean; created_at: string | null;
}
interface AiLogList {
  items: AiLog[]; total: number; all_total: number;
  success_rate: number; avg_latency_ms: number;
}

const TABS = ['运行概览', '账号管理', '平台趋势', '内容维护', '判定词表', '台词节点'] as const;
type Tab = (typeof TABS)[number];

const ROLE_CN: Record<string, string> = {
  student: '学生', teacher: '教师', admin: '管理员', guest: '访客',
};

const inp: React.CSSProperties = {
  padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 13,
};
const rowStyle: React.CSSProperties = {
  display: 'flex', gap: 14, alignItems: 'center', padding: '10px 12px',
  borderBottom: '1px solid #f2f0ec',
};

export default function AdminPage() {
  const nav = useNavigate();
  const { account, role } = useStore();
  const [tab, setTab] = useState<Tab>('运行概览');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [trend, setTrend] = useState<AdminTrend | null>(null);
  const [groups, setGroups] = useState<RuleGroup[]>([]);
  const [customWords, setCustomWords] = useState<CustomWord[]>([]);
  const [lines, setLines] = useState<ScriptLine[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioRow[]>([]);
  const [cards, setCards] = useState<CardRow[]>([]);
  const [aiLogs, setAiLogs] = useState<AiLogList | null>(null);
  const [msg, setMsg] = useState('');
  const [denied, setDenied] = useState(false);
  const [loading, setLoading] = useState(true);

  // 表单状态
  const [newUser, setNewUser] = useState({ username: '', password: '', nickname: '', role: 'student' });
  const [newWord, setNewWord] = useState({ group: 'empathy', word: '', note: '' });
  const [newLine, setNewLine] = useState({ text: '', emotion_bucket: 'mid', scenario_id: '' });
  const [accFilter, setAccFilter] = useState({ role: '', keyword: '' });
  const [accPage, setAccPage] = useState(1);
  const [accMeta, setAccMeta] = useState({ total: 0, pages: 0 });
  const [selected, setSelected] = useState<string[]>([]);
  // 内容维护
  const [cardForm, setCardForm] = useState({ id: '', title: '', category: '技巧', summary: '', content: '' });
  const [scForm, setScForm] = useState({
    id: '', name: '', age: 40, gender: '女', archetype: '', brief: '', system_prompt: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    const overviewResult = await apiGetResult<Overview>('/api/v1/admin/overview');
    const o = overviewResult.data;
    if (!o) {
      setLoading(false);
      // 403 走"无权限"页；其它错误（掉线/500）显示错误文案而不是伪装成无权限
      if (overviewResult.error?.forbidden) setDenied(true);
      else setMsg(describeApiError(overviewResult.error, '平台数据加载失败'));
      return;
    }
    setDenied(false);
    const [a, t, g, l, s, c, ai] = await Promise.all([
      apiGet<Paged<AccountRow>>(`/api/v1/admin/accounts?page=${accPage}&page_size=20`),
      apiGet<AdminTrend>('/api/v1/admin/trend'),
      apiGet<{ groups: RuleGroup[]; custom: CustomWord[] }>('/api/v1/admin/rule-words'),
      apiGet<{ items: ScriptLine[] }>('/api/v1/admin/script-lines'),
      apiGet<{ items: ScenarioRow[] }>('/api/v1/scenarios'),
      apiGet<{ items: CardRow[] }>('/api/v1/knowledge/cards'),
      apiGet<AiLogList>('/api/v1/admin/ai-logs?limit=50'),
    ]);
    setOverview(o);
    setAccounts(a?.items ?? []);
    setAccMeta({ total: a?.total ?? 0, pages: a?.pages ?? 0 });
    setTrend(t ?? null);
    setGroups(g?.groups ?? []);
    setCustomWords(g?.custom ?? []);
    setLines(l?.items ?? []);
    setScenarios(s?.items ?? []);
    setCards(c?.items ?? []);
    setAiLogs(ai ?? null);
    setLoading(false);
  }, [accPage]);

  useEffect(() => {
    if (account) void load();
  }, [account, load]);

  async function createAccount() {
    if (newUser.username.length < 3) { setMsg('用户名至少 3 位'); return; }
    if (newUser.password.length < 6) { setMsg('密码至少 6 位'); return; }
    const r = await apiSend('POST', '/api/v1/admin/accounts', newUser);
    setMsg(r.ok ? `已创建 ${newUser.username}` : r.msg);
    if (r.ok) {
      setNewUser({ username: '', password: '', nickname: '', role: 'student' });
      void load();
    }
  }

  async function toggleActive(row: AccountRow) {
    const r = await apiSend('PATCH', `/api/v1/admin/accounts/${row.id}/active`, { active: !row.is_active });
    setMsg(r.ok ? `${row.nickname} 已${row.is_active ? '停用' : '启用'}` : r.msg);
    if (r.ok) void load();
  }

  async function bulkToggle(active: boolean) {
    if (!selected.length) { setMsg('先勾选账号'); return; }
    const r = await apiSend<{ updated: number; failed: number }>(
      'POST', '/api/v1/admin/accounts/bulk-active', { account_ids: selected, active },
    );
    setMsg(r.ok ? `批量${active ? '启用' : '停用'} ${r.data?.updated ?? 0} 个账号` : r.msg);
    if (r.ok) { setSelected([]); void load(); }
  }

  async function addWord() {
    if (!newWord.word.trim()) { setMsg('词条不能为空'); return; }
    const r = await apiSend('POST', '/api/v1/admin/rule-words', newWord);
    setMsg(r.ok ? `词条「${newWord.word}」已生效` : r.msg);
    if (r.ok) { setNewWord({ ...newWord, word: '', note: '' }); void load(); }
  }

  async function disableWord(group: string, word: string) {
    const r = await apiSend('DELETE', `/api/v1/admin/rule-words/${group}/${encodeURIComponent(word)}`);
    setMsg(r.ok ? `已禁用「${word}」` : r.msg);
    if (r.ok) void load();
  }

  async function removeCustomWord(id: string, word: string) {
    const r = await apiSend('DELETE', `/api/v1/admin/rule-words/entry/${id}`);
    setMsg(r.ok ? `已删除「${word}」` : r.msg);
    if (r.ok) void load();
  }

  async function addLine() {
    if (!newLine.text.trim()) { setMsg('台词不能为空'); return; }
    const payload = {
      text: newLine.text,
      emotion_bucket: newLine.emotion_bucket,
      scenario_id: newLine.scenario_id || null,
    };
    const r = await apiSend('POST', '/api/v1/admin/script-lines', payload);
    setMsg(r.ok ? '台词已新增，下一轮对话即生效' : r.msg);
    if (r.ok) { setNewLine({ text: '', emotion_bucket: 'mid', scenario_id: '' }); void load(); }
  }

  async function removeLine(id: string) {
    const r = await apiSend('DELETE', `/api/v1/admin/script-lines/${id}`);
    setMsg(r.ok ? '台词已删除' : r.msg);
    if (r.ok) void load();
  }

  async function saveCard() {
    if (!cardForm.id.trim() || !cardForm.title.trim()) { setMsg('技巧卡需要 ID 与标题'); return; }
    const r = await apiSend('POST', '/api/v1/admin/cards', cardForm);
    setMsg(r.ok ? `技巧卡 ${cardForm.id} 已保存` : r.msg);
    if (r.ok) { setCardForm({ id: '', title: '', category: '技巧', summary: '', content: '' }); void load(); }
  }

  async function deleteCard(id: string) {
    const r = await apiSend('DELETE', `/api/v1/admin/cards/${id}`);
    setMsg(r.ok ? `技巧卡 ${id} 已删除` : r.msg);
    if (r.ok) void load();
  }

  async function saveScenario() {
    if (!scForm.id.trim() || !scForm.name.trim()) { setMsg('案例需要 ID 与姓名'); return; }
    const r = await apiSend('POST', '/api/v1/admin/scenarios', scForm);
    setMsg(r.ok ? `案例 ${scForm.id} 已保存` : r.msg);
    if (r.ok) {
      setScForm({ id: '', name: '', age: 40, gender: '女', archetype: '', brief: '', system_prompt: '' });
      void load();
    }
  }

  async function archiveScenario(id: string) {
    const r = await apiSend('DELETE', `/api/v1/admin/scenarios/${id}`);
    setMsg(r.ok ? `案例 ${id} 已下架` : r.msg);
    if (r.ok) void load();
  }

  const filteredAccounts = useMemo(() => {
    return accounts.filter((a) => {
      if (accFilter.role && a.role !== accFilter.role) return false;
      if (accFilter.keyword) {
        const q = accFilter.keyword.toLowerCase();
        if (!a.username.toLowerCase().includes(q) && !a.nickname.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [accounts, accFilter]);

  if (!account) {
    return (
      <div className="screen is-on">
        <div className="frame" style={{ padding: '48px 0' }}>
          <p>请先登录管理员账号。</p>
          <button className="btn-primary" type="button" onClick={() => nav('/login')}>去登录</button>
        </div>
      </div>
    );
  }

  if (denied) {
    return (
      <div className="screen is-on">
        <div className="frame" style={{ padding: '48px 0' }}>
          <h2>无权限访问</h2>
          <p style={{ color: 'var(--ink-3)' }}>
            当前账号角色为「{ROLE_CN[role] || role}」，管理后台仅对管理员开放。
          </p>
          <button className="btn-ghost" type="button" onClick={() => nav('/')}>回首页</button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen is-on">
      <div className="frame" style={{ display: 'block', padding: '28px 0 64px' }}>
        <div className="k">管理后台 · ADMIN</div>
        <h2 style={{ margin: '8px 0 4px' }}>{account.nickname}，欢迎回来</h2>
        <p style={{ color: 'var(--ink-3)', marginBottom: 16 }}>
          当前角色：管理员。可管理账号、内容（案例 / 技巧卡 / 判定词表 / 台词）与系统运行状态。
        </p>

        <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
          {TABS.map((t) => (
            <button key={t} type="button" className={t === tab ? 'btn-primary' : 'btn-ghost'}
              onClick={() => setTab(t)} style={{ padding: '6px 14px', fontSize: 13 }}>{t}</button>
          ))}
          <button className="btn-ghost" type="button" onClick={() => { void load(); }}
            style={{ padding: '6px 14px', fontSize: 13 }}>刷新</button>
        </div>

        {msg && <p style={{ color: '#b45309', marginBottom: 12, fontSize: 13 }}>{msg}</p>}
        {loading && <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>加载中…</p>}

        {/* ── 概览 ── */}
        {tab === '运行概览' && overview && (
          <>
            <div style={{ display: 'flex', gap: 30, flexWrap: 'wrap', marginBottom: 28 }}>
              {[
                ['账号总数', overview.accounts],
                ['教师数', overview.teachers],
                ['训练会话', overview.sessions],
                ['训练记录', overview.records],
                ['24h AI 调用', overview.ai_calls_24h],
                ['日调用上限', overview.daily_cap],
              ].map(([k, v]) => (
                <div key={String(k)}>
                  <div className="k">{k}</div>
                  <b style={{ fontSize: 24 }}>{v}</b>
                </div>
              ))}
            </div>

            <div className="k" style={{ marginBottom: 10 }}>AI 服务状态</div>
            <div style={{ fontSize: 13, marginBottom: 24, lineHeight: 1.9 }}>
              <div>密钥：{overview.ai_configured ? '已配置' : '未配置，规则模式运行'}</div>
              <div>模型链：{overview.model_chain.join(' → ')}</div>
              <div>运行环境：{overview.environment}</div>
              {aiLogs && (
                <div>
                  调用统计：共 {aiLogs.all_total} 次，成功率 {aiLogs.success_rate}%，
                  平均延迟 {aiLogs.avg_latency_ms} ms
                </div>
              )}
            </div>

            {aiLogs && aiLogs.items.length > 0 && (
              <>
                <div className="k" style={{ marginBottom: 10 }}>最近 AI 调用</div>
                <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid #f0eeea', borderRadius: 8 }}>
                  {aiLogs.items.slice(0, 20).map((log) => (
                    <div key={log.id} style={rowStyle}>
                      <span style={{ width: 70, fontSize: 12 }}>{log.purpose}</span>
                      <span style={{
                        width: 56, fontSize: 12,
                        color: log.status === 'ok' ? '#15803d' : '#b91c1c',
                      }}>{log.status}</span>
                      <span style={{ width: 120, fontSize: 12, color: 'var(--ink-3)' }}>{log.model || '—'}</span>
                      <span style={{ width: 70, fontSize: 12 }}>{log.latency_ms} ms</span>
                      <span style={{ width: 90, fontSize: 12, color: 'var(--ink-3)' }}>
                        {log.cache_hit ? '缓存命中' : log.used_ai ? '走模型' : '规则降级'}
                      </span>
                      <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-3)', textAlign: 'right' }}>
                        {log.created_at ? new Date(log.created_at).toLocaleString('zh-CN') : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {/* ── 账号管理 ── */}
        {tab === '账号管理' && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>新建账号（教务导入，不开放自助注册）</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 22 }}>
              <input placeholder="用户名（≥3 位）" value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} style={inp} />
              <input placeholder="密码（≥6 位）" type="password" value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} style={inp} />
              <input placeholder="昵称" value={newUser.nickname}
                onChange={(e) => setNewUser({ ...newUser, nickname: e.target.value })} style={inp} />
              <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                style={inp}>
                <option value="student">学生</option>
                <option value="teacher">教师</option>
                <option value="admin">管理员</option>
              </select>
              <button className="btn-primary" type="button" onClick={createAccount}
                style={{ padding: '8px 18px' }}>创建</button>
            </div>

            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
              <input placeholder="按用户名或昵称搜索" value={accFilter.keyword}
                onChange={(e) => { setAccFilter({ ...accFilter, keyword: e.target.value }); setAccPage(1); }}
                style={{ ...inp, minWidth: 200 }} />
              <select value={accFilter.role}
                onChange={(e) => { setAccFilter({ ...accFilter, role: e.target.value }); setAccPage(1); }} style={inp}>
                <option value="">全部角色</option>
                <option value="student">学生</option>
                <option value="teacher">教师</option>
                <option value="admin">管理员</option>
                <option value="guest">访客</option>
              </select>
              <span style={{ fontSize: 13, color: 'var(--ink-3)' }}>
                已选 {selected.length} / 共 {filteredAccounts.length}
              </span>
              <button className="btn-ghost" type="button" onClick={() => bulkToggle(false)}
                style={{ padding: '6px 14px', fontSize: 13 }}>批量停用</button>
              <button className="btn-ghost" type="button" onClick={() => bulkToggle(true)}
                style={{ padding: '6px 14px', fontSize: 13 }}>批量启用</button>
            </div>

            <div style={{ border: '1px solid #f0eeea', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{ ...rowStyle, background: '#faf9f7', fontSize: 12, color: 'var(--ink-3)' }}>
                <span style={{ width: 28 }} />
                <span style={{ width: 130 }}>用户名</span>
                <span style={{ width: 110 }}>昵称</span>
                <span style={{ width: 64 }}>角色</span>
                <span style={{ width: 64 }}>状态</span>
                <span style={{ flex: 1 }}>最近登录</span>
                <span style={{ width: 70 }}>操作</span>
              </div>
              {filteredAccounts.map((a) => (
                <div key={a.id} style={rowStyle}>
                  <input type="checkbox" checked={selected.includes(a.id)}
                    onChange={(e) => setSelected(e.target.checked
                      ? [...selected, a.id]
                      : selected.filter((x) => x !== a.id))}
                    style={{ width: 14, height: 14 }} />
                  <span style={{ width: 130, fontSize: 13 }}>{a.username}</span>
                  <span style={{ width: 110, fontSize: 13 }}>{a.nickname}</span>
                  <span style={{ width: 64, fontSize: 13 }}>{ROLE_CN[a.role] || a.role}</span>
                  <span style={{
                    width: 64, fontSize: 12,
                    color: a.is_active ? '#15803d' : '#b91c1c',
                  }}>{a.is_active ? '正常' : '停用'}</span>
                  <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-3)' }}>
                    {a.last_login_at ? new Date(a.last_login_at).toLocaleString('zh-CN') : '从未登录'}
                  </span>
                  {!a.is_guest && (
                    <button className="btn-ghost" type="button" onClick={() => toggleActive(a)}
                      style={{ padding: '3px 10px', fontSize: 12, width: 62 }}>
                      {a.is_active ? '停用' : '启用'}
                    </button>
                  )}
                </div>
              ))}
            </div>

            {accMeta.pages > 1 && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, fontSize: 13 }}>
                <button className="btn-ghost" type="button" disabled={accPage <= 1}
                  onClick={() => setAccPage((p) => Math.max(1, p - 1))}
                  style={{ padding: '4px 12px' }}>上一页</button>
                <span style={{ color: 'var(--ink-3)' }}>
                  第 {accPage} / {accMeta.pages} 页，共 {accMeta.total} 个账号
                </span>
                <button className="btn-ghost" type="button" disabled={accPage >= accMeta.pages}
                  onClick={() => setAccPage((p) => p + 1)}
                  style={{ padding: '4px 12px' }}>下一页</button>
              </div>
            )}
          </>
        )}

        {/* ── 平台趋势 ── */}
        {tab === '平台趋势' && trend && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>近 {trend.days} 天平均分</div>
            <AverageTrendChart points={trend.points} height={280} />

            <div className="k" style={{ margin: '26px 0 10px' }}>平台六维均值</div>
            <DimensionBarChart dims={trend.dimensions} />

            <div className="k" style={{ margin: '26px 0 10px' }}>角色分布</div>
            <DistributionPieChart
              data={Object.entries(trend.role_distribution).map(([r, count]) => ({
                name: ROLE_CN[r] || r,
                value: count,
              }))}
            />

            <div className="k" style={{ margin: '26px 0 10px' }}>案例使用热度</div>
            {trend.scenario_usage.length === 0 && (
              <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>暂无训练记录。</p>
            )}
            <ScenarioUsageChart data={trend.scenario_usage} />
          </>
        )}

        {/* ── 内容维护 ── */}
        {tab === '内容维护' && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>技巧卡（{cards.length} 张）</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
              <input placeholder="ID（如 T-20）" value={cardForm.id}
                onChange={(e) => setCardForm({ ...cardForm, id: e.target.value })} style={{ ...inp, width: 130 }} />
              <input placeholder="标题" value={cardForm.title}
                onChange={(e) => setCardForm({ ...cardForm, title: e.target.value })} style={{ ...inp, width: 180 }} />
              <select value={cardForm.category}
                onChange={(e) => setCardForm({ ...cardForm, category: e.target.value })} style={inp}>
                <option value="技巧">技巧</option>
                <option value="伦理">伦理</option>
              </select>
              <input placeholder="摘要" value={cardForm.summary}
                onChange={(e) => setCardForm({ ...cardForm, summary: e.target.value })}
                style={{ ...inp, flex: 1, minWidth: 200 }} />
              <button className="btn-primary" type="button" onClick={saveCard}
                style={{ padding: '8px 16px' }}>保存</button>
            </div>
            <div style={{ maxHeight: 240, overflow: 'auto', marginBottom: 26 }}>
              {cards.map((c) => (
                <div key={c.id} style={rowStyle}>
                  <span style={{ width: 70, fontSize: 12, color: 'var(--ink-3)' }}>{c.id}</span>
                  <span style={{ width: 200, fontSize: 13 }}>{c.title}</span>
                  <span style={{ width: 60, fontSize: 12, color: '#D97706' }}>{c.category}</span>
                  <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-3)' }}>
                    {c.summary.slice(0, 40)}
                  </span>
                  <button className="btn-ghost" type="button" onClick={() => deleteCard(c.id)}
                    style={{ padding: '3px 10px', fontSize: 12 }}>删除</button>
                </div>
              ))}
            </div>

            <div className="k" style={{ marginBottom: 10 }}>案例（{scenarios.length} 个）</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
              <input placeholder="ID（如 X-01）" value={scForm.id}
                onChange={(e) => setScForm({ ...scForm, id: e.target.value })} style={{ ...inp, width: 120 }} />
              <input placeholder="姓名" value={scForm.name}
                onChange={(e) => setScForm({ ...scForm, name: e.target.value })} style={{ ...inp, width: 120 }} />
              <input placeholder="年龄" type="number" value={scForm.age}
                onChange={(e) => setScForm({ ...scForm, age: Number(e.target.value) })}
                style={{ ...inp, width: 80 }} />
              <select value={scForm.gender}
                onChange={(e) => setScForm({ ...scForm, gender: e.target.value })} style={inp}>
                <option value="女">女</option>
                <option value="男">男</option>
              </select>
              <input placeholder="类型（如空巢老人）" value={scForm.archetype}
                onChange={(e) => setScForm({ ...scForm, archetype: e.target.value })}
                style={{ ...inp, width: 160 }} />
              <button className="btn-primary" type="button" onClick={saveScenario}
                style={{ padding: '8px 16px' }}>保存</button>
            </div>
            <div style={{ maxHeight: 240, overflow: 'auto' }}>
              {scenarios.map((s) => (
                <div key={s.id} style={rowStyle}>
                  <span style={{ width: 62, fontSize: 12, color: 'var(--ink-3)' }}>{s.id}</span>
                  <span style={{ width: 90, fontSize: 13 }}>{s.name}</span>
                  <span style={{ width: 130, fontSize: 12, color: 'var(--ink-3)' }}>{s.archetype}</span>
                  <span style={{ width: 84, fontSize: 12 }}>{s.difficulty_label}</span>
                  <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-3)' }}>
                    {s.active ? '在架' : '已下架'}
                  </span>
                  <button className="btn-ghost" type="button" onClick={() => archiveScenario(s.id)}
                    style={{ padding: '3px 10px', fontSize: 12 }}>下架</button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── 判定词表 ── */}
        {tab === '判定词表' && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>追加词条（危机与无望感组受保护，只能加不能禁）</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
              <select value={newWord.group}
                onChange={(e) => setNewWord({ ...newWord, group: e.target.value })} style={inp}>
                {groups.map((g) => (
                  <option key={g.group} value={g.group}>{g.label}（生效 {g.effective} 条）</option>
                ))}
              </select>
              <input placeholder="新词条" value={newWord.word}
                onChange={(e) => setNewWord({ ...newWord, word: e.target.value })} style={inp} />
              <input placeholder="备注（可选）" value={newWord.note}
                onChange={(e) => setNewWord({ ...newWord, note: e.target.value })}
                style={{ ...inp, minWidth: 160 }} />
              <button className="btn-primary" type="button" onClick={addWord}
                style={{ padding: '8px 16px' }}>追加</button>
            </div>

            <div className="k" style={{ marginBottom: 10 }}>九个词表分组</div>
            <div style={{ border: '1px solid #f0eeea', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
              {groups.map((g) => (
                <div key={g.group} style={rowStyle}>
                  <span style={{ width: 120, fontSize: 13 }}>{g.label}</span>
                  <span style={{ width: 80, fontSize: 12, color: 'var(--ink-3)' }}>基线 {g.baseline}</span>
                  <span style={{ width: 80, fontSize: 12 }}>生效 {g.effective}</span>
                  <span style={{
                    flex: 1, fontSize: 12,
                    color: g.protected ? '#b45309' : 'var(--ink-3)',
                  }}>
                    {g.protected ? '受保护：禁止禁用（安全边界）' : '可禁用'}
                  </span>
                  <input placeholder="输入词条回车禁用" disabled={g.protected}
                    onKeyDown={(e) => {
                      if (e.key !== 'Enter') return;
                      const v = (e.target as HTMLInputElement).value.trim();
                      if (v) void disableWord(g.group, v);
                      (e.target as HTMLInputElement).value = '';
                    }}
                    style={{ ...inp, width: 150, fontSize: 12 }} />
                </div>
              ))}
            </div>

            <div className="k" style={{ marginBottom: 10 }}>自定义词条（{customWords.length}）</div>
            {customWords.length === 0 && (
              <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>还没有自定义词条。</p>
            )}
            {customWords.map((w) => (
              <div key={w.id} style={rowStyle}>
                <span style={{ width: 110, fontSize: 12, color: 'var(--ink-3)' }}>{w.group_label}</span>
                <span style={{ width: 160, fontSize: 13 }}>{w.word}</span>
                <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-3)' }}>{w.note || '—'}</span>
                <button className="btn-ghost" type="button" onClick={() => removeCustomWord(w.id, w.word)}
                  style={{ padding: '3px 10px', fontSize: 12 }}>删除</button>
              </div>
            ))}
          </>
        )}

        {/* ── 台词节点 ── */}
        {tab === '台词节点' && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>
              新增台词（基线台词在代码里，库不可用时自动回落，不会让对话中断）
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
              <select value={newLine.emotion_bucket}
                onChange={(e) => setNewLine({ ...newLine, emotion_bucket: e.target.value })} style={inp}>
                <option value="low">低情绪</option>
                <option value="mid">中情绪</option>
                <option value="high">高情绪</option>
              </select>
              <select value={newLine.scenario_id}
                onChange={(e) => setNewLine({ ...newLine, scenario_id: e.target.value })} style={inp}>
                <option value="">全部角色通用</option>
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>{s.id} {s.name}</option>
                ))}
              </select>
              <input placeholder="台词内容" value={newLine.text}
                onChange={(e) => setNewLine({ ...newLine, text: e.target.value })}
                style={{ ...inp, flex: 1, minWidth: 240 }} />
              <button className="btn-primary" type="button" onClick={addLine}
                style={{ padding: '8px 16px' }}>新增</button>
            </div>

            <div className="k" style={{ marginBottom: 10 }}>已维护台词（{lines.length}）</div>
            {lines.length === 0 && (
              <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>
                暂无维护台词，当前使用代码内置的三档基线台词（每档 3 句）。
              </p>
            )}
            {lines.map((l) => (
              <div key={l.id} style={rowStyle}>
                <span style={{ width: 64, fontSize: 12 }}>{l.bucket_label}</span>
                <span style={{ width: 100, fontSize: 12, color: 'var(--ink-3)' }}>
                  {l.scenario_id || '通用'}
                </span>
                <span style={{ flex: 1, fontSize: 13 }}>{l.text}</span>
                <button className="btn-ghost" type="button" onClick={() => removeLine(l.id)}
                  style={{ padding: '3px 10px', fontSize: 12 }}>删除</button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * 管理后台
 *
 * 视觉与学生端（成长中心 P6）对齐：衬线大标题、等宽小字标签、
 * 纸色卡片、细分割线，样式走 `wb-*` 公共类。
 *
 * 六个视图：运行概览 / 账号管理 / 平台趋势 / 内容维护 / 判定词表 / 台词节点。
 * 权限在服务端（require_roles(admin)），本页只决定"看到什么入口"。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import { apiGet, apiGetResult, apiSend, describeApiError } from '../lib/authClient.ts';
import { useTabKeys } from '../lib/useTabKeys.ts';
import { ConfirmDialog, type ConfirmOptions } from '../components/ConfirmDialog.tsx';
import {
  AverageTrendChart,
  DimensionBarChart,
  DistributionPieChart,
  ScenarioUsageChart,
} from '../components/charts.tsx';

interface Overview {
  accounts: number; teachers: number; sessions: number; records: number;
  ai_calls_24h: number; ai_configured: boolean; model_chain: string[];
  daily_cap: number; environment: string;
}
interface AccountRow {
  id: string; username: string; nickname: string; role: string;
  is_active: boolean; is_guest: boolean; last_login_at: string | null;
}
interface Paged<T> {
  items: T[]; total: number; page: number; page_size: number; pages: number;
}
interface DimAvg { key: string; name: string; avg: number; count: number }
interface TrendPoint { date: string; sessions: number; avg_total: number }
interface ScenarioUsage {
  scenario_id: string; scenario_name: string; sessions: number; avg_total: number;
}
interface AdminTrend {
  days: number; points: TrendPoint[];
  role_distribution: Record<string, number>;
  scenario_usage: ScenarioUsage[]; dimensions: DimAvg[];
}
interface RuleGroup {
  group: string; label: string; baseline: number; effective: number; protected: boolean;
}
interface CustomWord {
  id: string; group: string; group_label: string; word: string;
  enabled: boolean; note: string;
}
interface ScriptLine {
  id: string; scenario_id: string | null; emotion_bucket: string;
  bucket_label: string; text: string; active: boolean;
}
interface ScenarioRow {
  id: string; name: string; age: number; gender: string; archetype: string;
  difficulty: number; difficulty_label: string; active: boolean;
}
interface CardRow { id: string; title: string; category: string; summary: string }
interface AiLog {
  id: string; purpose: string; status: string; model: string;
  latency_ms: number; degrade_reason: string | null;
  used_ai: boolean; cache_hit: boolean; created_at: string | null;
}
interface AuditRow {
  id: string; actor_name: string; actor_role: string;
  action: string; action_label: string;
  target_type: string; target_id: string;
  summary: string; created_at: string | null;
}

interface HeatCell { date: string; count: number; level: number }
interface HeatmapData {
  weeks: number; start: string; end: string;
  cells: HeatCell[]; total: number; active_days: number;
  total_days: number; thresholds: number[]; max_daily: number;
}

interface AiLogList {
  items: AiLog[]; total: number; all_total: number;
  success_rate: number; avg_latency_ms: number;
  ok_count: number; degraded_count: number; error_count: number;
}

const TABS = [
  { key: '运行概览', no: '01' },
  { key: '账号管理', no: '02' },
  { key: '平台趋势', no: '03' },
  { key: '内容维护', no: '04' },
  { key: '判定词表', no: '05' },
  { key: '台词节点', no: '06' },
  { key: '操作审计', no: '07' },
] as const;
type Tab = (typeof TABS)[number]['key'];

const ROLE_CN: Record<string, string> = {
  student: '学生', teacher: '教师', admin: '管理员', guest: '访客',
};
const ROLE_TAG: Record<string, string> = {
  student: 'ok', teacher: 'ok', admin: 'warn', guest: '',
};

export default function AdminPage() {
  const nav = useNavigate();
  const { account, role } = useStore();
  const [tab, setTab] = useState<Tab>('运行概览');
  const onTabKeyDown = useTabKeys(TABS, tab, setTab);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [accMeta, setAccMeta] = useState({ total: 0, pages: 0 });
  const [accPage, setAccPage] = useState(1);
  const [trend, setTrend] = useState<AdminTrend | null>(null);
  const [groups, setGroups] = useState<RuleGroup[]>([]);
  const [customWords, setCustomWords] = useState<CustomWord[]>([]);
  const [lines, setLines] = useState<ScriptLine[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioRow[]>([]);
  const [cards, setCards] = useState<CardRow[]>([]);
  const [aiLogs, setAiLogs] = useState<AiLogList | null>(null);
  const [audits, setAudits] = useState<AuditRow[]>([]);
  const [heat, setHeat] = useState<HeatmapData | null>(null);
  const [msg, setMsg] = useState('');
  const [msgKind, setMsgKind] = useState<'ok' | 'err'>('ok');
  const [denied, setDenied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState<ConfirmOptions | null>(null);

  const [newUser, setNewUser] = useState({
    username: '', password: '', nickname: '', role: 'student',
  });
  const [newWord, setNewWord] = useState({ group: 'empathy', word: '', note: '' });
  const [newLine, setNewLine] = useState({
    text: '', emotion_bucket: 'mid', scenario_id: '',
  });
  // 访客是每次访问即时创建的临时账号，量大且无管理价值，默认隐藏
  const [accFilter, setAccFilter] = useState({ role: '', keyword: '', hideGuests: true });
  const [selected, setSelected] = useState<string[]>([]);
  const [cardForm, setCardForm] = useState({
    id: '', title: '', category: '技巧', summary: '', content: '',
  });
  const [scForm, setScForm] = useState({
    id: '', name: '', age: 40, gender: '女', archetype: '',
    brief: '', system_prompt: '',
  });

  /** 统一提示：成功绿色、失败朱红，3 秒后自动消失 */
  const notify = useCallback((text: string, ok = true) => {
    setMsg(text);
    setMsgKind(ok ? 'ok' : 'err');
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const overviewResult = await apiGetResult<Overview>('/api/v1/admin/overview');
    const o = overviewResult.data;
    if (!o) {
      setLoading(false);
      if (overviewResult.error?.forbidden) setDenied(true);
      else notify(describeApiError(overviewResult.error, '平台数据加载失败'), false);
      return;
    }
    setDenied(false);
    const [a, t, g, l, s, c, ai] = await Promise.all([
      apiGet<Paged<AccountRow>>(
        `/api/v1/admin/accounts?page=${accPage}&page_size=20`
        + `&include_guests=${accFilter.hideGuests ? 'false' : 'true'}`
        + (accFilter.role ? `&role=${accFilter.role}` : ''),
      ),
      apiGet<AdminTrend>('/api/v1/admin/trend'),
      apiGet<{ groups: RuleGroup[]; custom: CustomWord[] }>('/api/v1/admin/rule-words'),
      apiGet<{ items: ScriptLine[] }>('/api/v1/admin/script-lines'),
      apiGet<{ items: ScenarioRow[] }>('/api/v1/scenarios'),
      apiGet<{ items: CardRow[] }>('/api/v1/knowledge/cards'),
      apiGet<AiLogList>('/api/v1/admin/ai-logs?limit=50'),
    ]);
    void apiGet<{ items: AuditRow[] }>('/api/v1/admin/audit-logs?limit=100').then((r) => {
      setAudits(r?.items ?? []);
    });
    void apiGet<HeatmapData>('/api/v1/admin/heatmap?weeks=18').then((r) => {
      setHeat(r ?? null);
    });
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
  }, [accPage, accFilter.hideGuests, accFilter.role, notify]);

  useEffect(() => { if (account) void load(); }, [account, load]);

  async function createAccount() {
    if (newUser.username.length < 3) { notify('用户名至少 3 位', false); return; }
    if (newUser.password.length < 6) { notify('密码至少 6 位', false); return; }
    const r = await apiSend('POST', '/api/v1/admin/accounts', newUser);
    notify(r.ok ? `已创建 ${newUser.username}` : r.msg, r.ok);
    if (r.ok) {
      setNewUser({ username: '', password: '', nickname: '', role: 'student' });
      void load();
    }
  }

  function toggleActive(row: AccountRow) {
    if (row.is_active) {
      setConfirm({
        title: '停用账号',
        message: `停用后 ${row.nickname}（${row.username}）将无法登录。确定停用？`,
        confirmLabel: '停用', danger: true,
        onConfirm: async () => {
          const r = await apiSend('PATCH', `/api/v1/admin/accounts/${row.id}/active`,
            { active: false });
          notify(r.ok ? `${row.nickname} 已停用` : r.msg, r.ok);
          if (r.ok) void load();
        },
      });
      return;
    }
    void (async () => {
      const r = await apiSend('PATCH', `/api/v1/admin/accounts/${row.id}/active`,
        { active: true });
      notify(r.ok ? `${row.nickname} 已启用` : r.msg, r.ok);
      if (r.ok) void load();
    })();
  }

  function bulkToggle(active: boolean) {
    if (!selected.length) { notify('先勾选账号', false); return; }
    const run = async () => {
      const r = await apiSend<{ updated: number; failed: number }>(
        'POST', '/api/v1/admin/accounts/bulk-active',
        { account_ids: selected, active },
      );
      notify(r.ok ? `批量${active ? '启用' : '停用'} ${r.data?.updated ?? 0} 个账号` : r.msg, r.ok);
      if (r.ok) { setSelected([]); void load(); }
    };
    if (active) { void run(); return; }
    setConfirm({
      title: `批量停用 ${selected.length} 个账号`,
      message: '这些账号将立即无法登录。请确认已核对勾选范围。',
      confirmLabel: '批量停用', danger: true, onConfirm: run,
    });
  }

  async function addWord() {
    if (!newWord.word.trim()) { notify('词条不能为空', false); return; }
    const r = await apiSend('POST', '/api/v1/admin/rule-words', newWord);
    notify(r.ok ? `词条「${newWord.word}」已生效` : r.msg, r.ok);
    if (r.ok) { setNewWord({ ...newWord, word: '', note: '' }); void load(); }
  }

  async function disableWord(group: string, word: string) {
    const r = await apiSend('DELETE',
      `/api/v1/admin/rule-words/${group}/${encodeURIComponent(word)}`);
    notify(r.ok ? `已禁用「${word}」` : r.msg, r.ok);
    if (r.ok) void load();
  }

  function removeCustomWord(id: string, word: string) {
    setConfirm({
      title: '删除自定义词条',
      message: `词条「${word}」将被彻底删除，不再参与判定。确定删除？`,
      confirmLabel: '删除', danger: true,
      onConfirm: async () => {
        const r = await apiSend('DELETE', `/api/v1/admin/rule-words/entry/${id}`);
        notify(r.ok ? `已删除「${word}」` : r.msg, r.ok);
        if (r.ok) void load();
      },
    });
  }

  async function addLine() {
    if (!newLine.text.trim()) { notify('台词不能为空', false); return; }
    const r = await apiSend('POST', '/api/v1/admin/script-lines', {
      text: newLine.text,
      emotion_bucket: newLine.emotion_bucket,
      scenario_id: newLine.scenario_id || null,
    });
    notify(r.ok ? '台词已新增，下一轮对话生效' : r.msg, r.ok);
    if (r.ok) { setNewLine({ text: '', emotion_bucket: 'mid', scenario_id: '' }); void load(); }
  }

  function removeLine(id: string) {
    setConfirm({
      title: '删除台词',
      message: '删除后该情绪档回落到代码内置的基线台词。确定删除？',
      confirmLabel: '删除', danger: true,
      onConfirm: async () => {
        const r = await apiSend('DELETE', `/api/v1/admin/script-lines/${id}`);
        notify(r.ok ? '台词已删除' : r.msg, r.ok);
        if (r.ok) void load();
      },
    });
  }

  async function saveCard() {
    if (!cardForm.id.trim() || !cardForm.title.trim()) {
      notify('技巧卡需要 ID 与标题', false);
      return;
    }
    const r = await apiSend('POST', '/api/v1/admin/cards', cardForm);
    notify(r.ok ? `技巧卡 ${cardForm.id} 已保存` : r.msg, r.ok);
    if (r.ok) {
      setCardForm({ id: '', title: '', category: '技巧', summary: '', content: '' });
      void load();
    }
  }

  function deleteCard(id: string) {
    setConfirm({
      title: '删除技巧卡',
      message: `技巧卡 ${id} 将被物理删除，知识库不再展示。确定删除？`,
      confirmLabel: '删除', danger: true,
      onConfirm: async () => {
        const r = await apiSend('DELETE', `/api/v1/admin/cards/${id}`);
        notify(r.ok ? `技巧卡 ${id} 已删除` : r.msg, r.ok);
        if (r.ok) void load();
      },
    });
  }

  async function saveScenario() {
    if (!scForm.id.trim() || !scForm.name.trim()) {
      notify('案例需要 ID 与姓名', false);
      return;
    }
    const r = await apiSend('POST', '/api/v1/admin/scenarios', scForm);
    notify(r.ok ? `案例 ${scForm.id} 已保存` : r.msg, r.ok);
    if (r.ok) {
      setScForm({ id: '', name: '', age: 40, gender: '女', archetype: '',
        brief: '', system_prompt: '' });
      void load();
    }
  }

  function archiveScenario(id: string) {
    setConfirm({
      title: '下架案例',
      message: `案例 ${id} 将不再出现在选角列表，历史记录仍可查看。确定下架？`,
      confirmLabel: '下架', danger: true,
      onConfirm: async () => {
        const r = await apiSend('DELETE', `/api/v1/admin/scenarios/${id}`);
        notify(r.ok ? `案例 ${id} 已下架` : r.msg, r.ok);
        if (r.ok) void load();
      },
    });
  }

  const filteredAccounts = useMemo(() => accounts.filter((a) => {
    if (accFilter.hideGuests && a.is_guest) return false;
    if (accFilter.role && a.role !== accFilter.role) return false;
    if (accFilter.keyword) {
      const q = accFilter.keyword.toLowerCase();
      return a.username.toLowerCase().includes(q) || a.nickname.toLowerCase().includes(q);
    }
    return true;
  }), [accounts, accFilter]);

  if (!account) {
    return (
      <div className="screen is-on">
        <div className="wb-frame">
          <div className="wb-empty">
            <b>需要登录</b>
            管理后台仅对管理员开放。
            <div style={{ marginTop: 16 }}>
              <button className="btn-primary" type="button" onClick={() => nav('/login')}>
                去登录
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (denied) {
    return (
      <div className="screen is-on">
        <div className="wb-frame">
          <div className="wb-empty">
            <b>无权限访问</b>
            当前账号角色为「{ROLE_CN[role] || role}」，管理后台仅对管理员开放。
            <div style={{ marginTop: 16 }}>
              <button className="btn-ghost" type="button" onClick={() => nav('/')}>
                回首页
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen is-on">
      <div className="wb-frame" style={{ paddingBottom: 72 }}>
        <div className="wb-head">
          <div className="k">管理后台 · Admin</div>
          <h2>{account.nickname}，欢迎回来</h2>
          <p className="sub">
            可管理账号、内容（案例 / 技巧卡 / 判定词表 / 台词）与系统运行状态。
          </p>
          <div className="meta">
            {overview
              ? `${overview.accounts} 个账号 · ${overview.sessions} 次会话 · 环境 ${overview.environment}`
              : '数据加载中'}
          </div>
        </div>

        <div className="wb-tabs" role="tablist" aria-label="管理后台视图"
          onKeyDown={onTabKeyDown}>
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              id={`tab-${t.key}`}
              aria-controls="panel-admin"
              aria-selected={tab === t.key}
              tabIndex={tab === t.key ? 0 : -1}
              className="wb-tab"
              onClick={() => setTab(t.key)}
            >
              <span className="no">{t.no}</span>
              {t.key}
            </button>
          ))}
        </div>

        {msg && <div className={`wb-alert ${msgKind}`}>{msg}</div>}
        {loading && <div className="wb-alert info">正在读取平台数据…</div>}

        {/* ── 01 运行概览 ── */}
        <div role="tabpanel" id="panel-admin" aria-labelledby={`tab-${tab}`}>
        {tab === '运行概览' && overview && (
          <>
            <div className="wb-metrics">
              <div className="wb-metric">
                <div className="k">账号总数</div>
                <div className="n">{overview.accounts}</div>
                <div className="d">含教师 {overview.teachers} 人</div>
              </div>
              <div className="wb-metric">
                <div className="k">训练会话</div>
                <div className="n">{overview.sessions}</div>
                <div className="d">{overview.records} 条训练记录</div>
              </div>
              <div className="wb-metric">
                <div className="k">24h AI 调用</div>
                <div className="n">{overview.ai_calls_24h}</div>
                <div className="d">上限 {overview.daily_cap} 次/日</div>
              </div>
              <div className="wb-metric">
                <div className="k">服务可用率</div>
                <div className="n">{aiLogs ? `${aiLogs.success_rate}%` : '—'}</div>
                <div className="d">
                  {aiLogs
                    ? `降级 ${aiLogs.degraded_count} · 报错 ${aiLogs.error_count}`
                    : '暂无数据'}
                </div>
              </div>
            </div>

            <div className="wb-grid">
              <div className="wb-panel">
                <div className="wb-panel-h">
                  <span>AI 服务状态</span>
                  <span className="hint">
                    {overview.ai_configured ? '已配置密钥' : '未配置，规则模式'}
                  </span>
                </div>
                <div className="wb-row">
                  <span className="name">主模型链</span>
                  <span className="spacer" />
                  <span className="mono">{overview.model_chain.join(' → ')}</span>
                </div>
                <div className="wb-row">
                  <span className="name">运行环境</span>
                  <span className="spacer" />
                  <span className="tag">{overview.environment}</span>
                </div>
                <div className="wb-row">
                  <span className="name">日调用上限</span>
                  <span className="spacer" />
                  <span className="mono">{overview.daily_cap} 次</span>
                </div>
                <div className="wb-row">
                  <span className="name">累计调用</span>
                  <span className="spacer" />
                  <span className="mono">{aiLogs?.all_total ?? '—'} 次</span>
                </div>
                <div className="wb-row">
                  <span className="name">走模型 / 规则降级</span>
                  <span className="spacer" />
                  <span className="mono">
                    {aiLogs ? `${aiLogs.ok_count} / ${aiLogs.degraded_count}` : '—'}
                  </span>
                </div>
                <div className="wb-row">
                  <span className="name">平均响应</span>
                  <span className="spacer" />
                  <span className="mono">
                    {aiLogs ? `${aiLogs.avg_latency_ms} ms` : '—'}
                  </span>
                </div>
              </div>

              <div className="wb-panel">
                <div className="wb-panel-h">最近 AI 调用</div>
                {(!aiLogs || aiLogs.items.length === 0) && (
                  <div className="wb-empty">
                    <b>暂无调用记录</b>
                    完成一次训练后，AI 链路的调用会记录在这里。
                  </div>
                )}
                {(aiLogs?.items ?? []).slice(0, 10).map((log) => (
                  <div key={log.id} className="wb-row">
                    <span className="tag">{log.purpose}</span>
                    <span className="mono" style={{
                      color: log.status === 'ok' ? 'var(--green)' : 'var(--proof)',
                    }}>
                      {log.status}
                    </span>
                    <span className="spacer" />
                    <span className="mono">{log.latency_ms}ms</span>
                    <span className="mono" style={{ color: 'var(--ink-4)' }}>
                      {log.cache_hit ? '缓存' : log.used_ai ? '模型' : '降级'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {/* ── 02 账号管理 ── */}
        {tab === '账号管理' && (
          <>
            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>新建账号</span>
                <span className="hint">教务统一导入，不开放自助注册</span>
              </div>
              <div className="wb-form">
                <input className="wb-input" placeholder="用户名（≥3 位）"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} />
                <input className="wb-input" placeholder="密码（≥6 位）" type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} />
                <input className="wb-input" placeholder="昵称"
                  value={newUser.nickname}
                  onChange={(e) => setNewUser({ ...newUser, nickname: e.target.value })} />
                <select className="wb-input" value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
                  <option value="student">学生</option>
                  <option value="teacher">教师</option>
                  <option value="admin">管理员</option>
                </select>
                <button className="btn-primary" type="button" onClick={createAccount}
                  style={{ padding: '9px 20px' }}>
                  创建
                </button>
              </div>
            </div>

            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>账号列表</span>
                <span className="hint">
                  共 {accMeta.total} 个 · 已选 {selected.length}
                </span>
              </div>

              <div className="wb-form">
                <input className="wb-input" style={{ flex: 1, minWidth: 180 }}
                  placeholder="按用户名或昵称搜索"
                  value={accFilter.keyword}
                  onChange={(e) => {
                    setAccFilter({ ...accFilter, keyword: e.target.value });
                    setAccPage(1);
                  }} />
                <select className="wb-input" value={accFilter.role}
                  onChange={(e) => {
                    setAccFilter({ ...accFilter, role: e.target.value });
                    setAccPage(1);
                  }}>
                  <option value="">全部角色</option>
                  <option value="student">学生</option>
                  <option value="teacher">教师</option>
                  <option value="admin">管理员</option>
                  <option value="guest">访客</option>
                </select>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                  fontSize: 12.5, color: 'var(--ink-2)', cursor: 'pointer',
                  minHeight: 40 }}>
                  <input type="checkbox" checked={accFilter.hideGuests}
                    onChange={(e) => {
                      setAccFilter({ ...accFilter, hideGuests: e.target.checked });
                      setAccPage(1);
                    }}
                    style={{ width: 15, height: 15, cursor: 'pointer' }} />
                  隐藏访客
                </label>
                <button className="btn-ghost" type="button" onClick={() => bulkToggle(false)}
                  style={{ padding: '9px 16px' }}>
                  批量停用
                </button>
                <button className="btn-ghost" type="button" onClick={() => bulkToggle(true)}
                  style={{ padding: '9px 16px' }}>
                  批量启用
                </button>
              </div>

              {filteredAccounts.map((a) => (
                <div key={a.id} className="wb-row">
                  <input type="checkbox" checked={selected.includes(a.id)}
                    onChange={(e) => setSelected(e.target.checked
                      ? [...selected, a.id]
                      : selected.filter((x) => x !== a.id))}
                    aria-label={`选择 ${a.username}`}
                    style={{ width: 15, height: 15, cursor: 'pointer' }} />
                  <span className="name">{a.nickname}</span>
                  <span className="mono">{a.username}</span>
                  <span className={`tag ${ROLE_TAG[a.role] ?? ''}`}>
                    {ROLE_CN[a.role] || a.role}
                  </span>
                  <span className="spacer" />
                  <span className="mono" style={{ color: 'var(--ink-4)' }}>
                    {a.last_login_at
                      ? `登录 ${new Date(a.last_login_at).toLocaleDateString('zh-CN')}`
                      : '从未登录'}
                  </span>
                  <span className={`tag ${a.is_active ? 'ok' : 'warn'}`}>
                    {a.is_active ? '正常' : '停用'}
                  </span>
                  {!a.is_guest && (
                    <button className="btn-ghost" type="button" onClick={() => toggleActive(a)}
                      style={{ padding: '5px 12px', fontSize: 12 }}>
                      {a.is_active ? '停用' : '启用'}
                    </button>
                  )}
                </div>
              ))}

              {accMeta.pages > 1 && (
                <div className="wb-pager">
                  <button type="button" disabled={accPage <= 1}
                    onClick={() => setAccPage((p) => Math.max(1, p - 1))}>
                    上一页
                  </button>
                  <span>第 {accPage} / {accMeta.pages} 页</span>
                  <button type="button" disabled={accPage >= accMeta.pages}
                    onClick={() => setAccPage((p) => p + 1)}>
                    下一页
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {/* ── 03 平台趋势 ── */}
        {tab === '平台趋势' && trend && (
          <>
            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>近 {trend.days} 天平均分</span>
                <span className="hint">折线为均分，柱状为训练次数</span>
              </div>
              <AverageTrendChart points={trend.points} height={300} />
            </div>

            {heat && (
              <div className="wb-panel">
                <div className="wb-panel-h">
                  <span>训练频率热力图</span>
                  <span className="hint">
                    近 {heat.weeks} 周 · {heat.total} 次训练 ·{' '}
                    {heat.active_days}/{heat.total_days} 天有训练
                  </span>
                </div>
                <div className="heat-wrap heat-lg">
                  <div className="heat-days">
                    {['一', '', '三', '', '五', '', '日'].map((d, i) => (
                      <span key={i}>{d}</span>
                    ))}
                  </div>
                  <div className="heat-cells">
                    {heat.cells.map((c) => (
                      <span
                        key={c.date}
                        className={'hc' + (c.level > 0 ? ' l' + c.level : '')}
                        title={`${c.date} · ${c.count} 次训练`}
                      />
                    ))}
                  </div>
                </div>
                <div className="heat-legend">
                  <span>少</span>
                  <i style={{ background: '#EFE9DE' }} />
                  <i style={{ background: '#C6D9CB' }} />
                  <i style={{ background: '#8FBAA0' }} />
                  <i style={{ background: '#4E8A6B' }} />
                  <i style={{ background: '#2F5D50' }} />
                  <span>多</span>
                  <span style={{ marginLeft: 14, color: 'var(--ink-4)' }}>
                    单日最多 {heat.max_daily} 次
                  </span>
                </div>
              </div>
            )}

            <div className="wb-grid">
              <div className="wb-panel">
                <div className="wb-panel-h">平台六维均值</div>
                <DimensionBarChart dims={trend.dimensions} height={260} />
              </div>
              <div className="wb-panel">
                <div className="wb-panel-h">角色分布</div>
                <DistributionPieChart
                  data={Object.entries(trend.role_distribution).map(([r, count]) => ({
                    name: ROLE_CN[r] || r, value: count,
                  }))}
                  height={260}
                />
              </div>
            </div>

            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>案例使用热度</span>
                <span className="hint">按练习次数排序</span>
              </div>
              <ScenarioUsageChart data={trend.scenario_usage} height={300} />
            </div>
          </>
        )}

        {/* ── 04 内容维护 ── */}
        {tab === '内容维护' && (
          <>
            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>技巧卡</span>
                <span className="hint">共 {cards.length} 张</span>
              </div>
              <div className="wb-form">
                <input className="wb-input" style={{ width: 130 }} placeholder="ID（T-20）"
                  value={cardForm.id}
                  onChange={(e) => setCardForm({ ...cardForm, id: e.target.value })} />
                <input className="wb-input" style={{ width: 180 }} placeholder="标题"
                  value={cardForm.title}
                  onChange={(e) => setCardForm({ ...cardForm, title: e.target.value })} />
                <select className="wb-input" value={cardForm.category}
                  onChange={(e) => setCardForm({ ...cardForm, category: e.target.value })}>
                  <option value="技巧">技巧</option>
                  <option value="伦理">伦理</option>
                </select>
                <input className="wb-input" style={{ flex: 1, minWidth: 180 }}
                  placeholder="摘要" value={cardForm.summary}
                  onChange={(e) => setCardForm({ ...cardForm, summary: e.target.value })} />
                <button className="btn-primary" type="button" onClick={saveCard}
                  style={{ padding: '9px 18px' }}>
                  保存
                </button>
              </div>
              {cards.map((c) => (
                <div key={c.id} className="wb-row">
                  <span className="mono" style={{ width: 52 }}>{c.id}</span>
                  <span className="name">{c.title}</span>
                  <span className="tag">{c.category}</span>
                  <span className="spacer" />
                  <span className="mono" style={{ color: 'var(--ink-4)',
                    maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap' }}>
                    {c.summary}
                  </span>
                  <button className="btn-ghost" type="button" onClick={() => deleteCard(c.id)}
                    style={{ padding: '5px 12px', fontSize: 12 }}>
                    删除
                  </button>
                </div>
              ))}
            </div>

            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>案例</span>
                <span className="hint">共 {scenarios.length} 个</span>
              </div>
              <div className="wb-form">
                <input className="wb-input" style={{ width: 110 }} placeholder="ID（X-01）"
                  value={scForm.id}
                  onChange={(e) => setScForm({ ...scForm, id: e.target.value })} />
                <input className="wb-input" style={{ width: 110 }} placeholder="姓名"
                  value={scForm.name}
                  onChange={(e) => setScForm({ ...scForm, name: e.target.value })} />
                <input className="wb-input" style={{ width: 78 }} placeholder="年龄"
                  type="number" value={scForm.age}
                  onChange={(e) => setScForm({ ...scForm, age: Number(e.target.value) })} />
                <select className="wb-input" value={scForm.gender}
                  onChange={(e) => setScForm({ ...scForm, gender: e.target.value })}>
                  <option value="女">女</option>
                  <option value="男">男</option>
                </select>
                <input className="wb-input" style={{ width: 150 }} placeholder="类型（空巢老人）"
                  value={scForm.archetype}
                  onChange={(e) => setScForm({ ...scForm, archetype: e.target.value })} />
                <button className="btn-primary" type="button" onClick={saveScenario}
                  style={{ padding: '9px 18px' }}>
                  保存
                </button>
              </div>
              {scenarios.map((s) => (
                <div key={s.id} className="wb-row">
                  <span className="mono" style={{ width: 52 }}>{s.id}</span>
                  <span className="name">{s.name}</span>
                  <span className="mono">{s.archetype}</span>
                  <span className="spacer" />
                  <span className="tag">{s.difficulty_label}</span>
                  <span className={`tag ${s.active ? 'ok' : 'warn'}`}>
                    {s.active ? '在架' : '已下架'}
                  </span>
                  <button className="btn-ghost" type="button" onClick={() => archiveScenario(s.id)}
                    style={{ padding: '5px 12px', fontSize: 12 }}>
                    下架
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── 05 判定词表 ── */}
        {tab === '判定词表' && (
          <>
            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>追加词条</span>
                <span className="hint">危机与无望感组受保护，只能加不能禁</span>
              </div>
              <div className="wb-form">
                <select className="wb-input" value={newWord.group}
                  onChange={(e) => setNewWord({ ...newWord, group: e.target.value })}>
                  {groups.map((g) => (
                    <option key={g.group} value={g.group}>
                      {g.label}（生效 {g.effective}）
                    </option>
                  ))}
                </select>
                <input className="wb-input" placeholder="新词条" value={newWord.word}
                  onChange={(e) => setNewWord({ ...newWord, word: e.target.value })} />
                <input className="wb-input" style={{ flex: 1, minWidth: 160 }}
                  placeholder="备注（可选）" value={newWord.note}
                  onChange={(e) => setNewWord({ ...newWord, note: e.target.value })} />
                <button className="btn-primary" type="button" onClick={addWord}
                  style={{ padding: '9px 18px' }}>
                  追加
                </button>
              </div>

              <div className="wb-panel-h" style={{ marginTop: 8 }}>九个词表分组</div>
              {groups.map((g) => (
                <div key={g.group} className="wb-row">
                  <span className="name" style={{ width: 110 }}>{g.label}</span>
                  <span className="mono">基线 {g.baseline}</span>
                  <span className="mono">生效 {g.effective}</span>
                  <span className="spacer" />
                  <span className={`tag ${g.protected ? 'warn' : ''}`}>
                    {g.protected ? '受保护' : '可禁用'}
                  </span>
                  <input className="wb-input" style={{ width: 140, fontSize: 12 }}
                    placeholder={g.protected ? '禁止禁用' : '输入词条回车禁用'}
                    disabled={g.protected}
                    onKeyDown={(e) => {
                      if (e.key !== 'Enter') return;
                      const v = (e.target as HTMLInputElement).value.trim();
                      if (v) void disableWord(g.group, v);
                      (e.target as HTMLInputElement).value = '';
                    }} />
                </div>
              ))}
            </div>

            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>自定义词条</span>
                <span className="hint">共 {customWords.length} 条</span>
              </div>
              {customWords.length === 0 && (
                <div className="wb-empty">
                  <b>还没有自定义词条</b>
                  在上方选择分组并追加词条后，会出现在这里。
                </div>
              )}
              {customWords.map((w) => (
                <div key={w.id} className="wb-row">
                  <span className="tag">{w.group_label}</span>
                  <span className="name">{w.word}</span>
                  <span className="spacer" />
                  <span className="mono" style={{ color: 'var(--ink-4)' }}>
                    {w.note || '—'}
                  </span>
                  <button className="btn-ghost" type="button"
                    onClick={() => removeCustomWord(w.id, w.word)}
                    style={{ padding: '5px 12px', fontSize: 12 }}>
                    删除
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── 07 操作审计 ── */}
        {tab === '操作审计' && (
          <div className="wb-panel">
            <div className="wb-panel-h">
              <span>管理操作审计</span>
              <span className="hint">共 {audits.length} 条 · 最近 100 条</span>
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.7,
              margin: '0 0 12px' }}>
              记录账号启停、内容增删、词表与台词修改等管理动作，
              便于追责与排查。摘要已对口令等敏感字段打码。
            </p>
            {audits.length === 0 && (
              <div className="wb-empty">
                <b>暂无审计记录</b>
                执行一次管理操作（如新建账号、下架案例）后会出现。
              </div>
            )}
            {audits.map((a) => (
              <div key={a.id} className="wb-row">
                <span className="tag">{a.action_label}</span>
                <span className="name">{a.actor_name}</span>
                <span className="mono" style={{ maxWidth: 380, overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {a.summary || '—'}
                </span>
                <span className="spacer" />
                <span className="mono" style={{ color: 'var(--ink-4)' }}>
                  {a.created_at
                    ? new Date(a.created_at).toLocaleString('zh-CN')
                    : ''}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* ── 06 台词节点 ── */}
        {tab === '台词节点' && (
          <div className="wb-panel">
            <div className="wb-panel-h">
              <span>维护台词</span>
              <span className="hint">库不可用时自动回落到代码内置基线</span>
            </div>
            <div className="wb-form">
              <select className="wb-input" value={newLine.emotion_bucket}
                onChange={(e) => setNewLine({ ...newLine, emotion_bucket: e.target.value })}>
                <option value="low">低情绪</option>
                <option value="mid">中情绪</option>
                <option value="high">高情绪</option>
              </select>
              <select className="wb-input" value={newLine.scenario_id}
                onChange={(e) => setNewLine({ ...newLine, scenario_id: e.target.value })}>
                <option value="">全部角色通用</option>
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>{s.id} {s.name}</option>
                ))}
              </select>
              <input className="wb-input" style={{ flex: 1, minWidth: 220 }}
                placeholder="台词内容" value={newLine.text}
                onChange={(e) => setNewLine({ ...newLine, text: e.target.value })} />
              <button className="btn-primary" type="button" onClick={addLine}
                style={{ padding: '9px 18px' }}>
                新增
              </button>
            </div>

            <div className="wb-panel-h" style={{ marginTop: 8 }}>
              已维护台词（{lines.length}）
            </div>
            {lines.length === 0 && (
              <div className="wb-empty">
                <b>暂无维护台词</b>
                当前使用代码内置的三档基线台词（每档 3 句）。新增后优先使用这里的内容。
              </div>
            )}
            {lines.map((l) => (
              <div key={l.id} className="wb-row">
                <span className="tag">{l.bucket_label}</span>
                <span className="mono" style={{ width: 64 }}>
                  {l.scenario_id || '通用'}
                </span>
                <span className="name" style={{ fontWeight: 400, flex: 1 }}>{l.text}</span>
                <button className="btn-ghost" type="button" onClick={() => removeLine(l.id)}
                  style={{ padding: '5px 12px', fontSize: 12 }}>
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
        </div>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        options={confirm}
        onClose={() => setConfirm(null)}
      />
    </div>
  );
}

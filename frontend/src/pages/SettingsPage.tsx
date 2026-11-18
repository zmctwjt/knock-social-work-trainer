/**
 * 10 设置
 * 默认难度 · 无剧透 · AI 模式与诊断 · 依据显示 · 数据导出与清除
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import {
  loadSettingsLocal, saveSettingsLocal, exportCsv, downloadText, purgeLocal,
  dbReady, type UserSettings,
} from '../lib/db.ts';
import {
  setAiEnabled, fetchUsage, selftest, probeAi, getAiBase, setAiBase,
  type AiHealth,
} from '../lib/aiClient.ts';
import { useAiStatus } from '../hooks/useSession.ts';
import { SKILL_CARDS, ETHICS } from '../data/knowledge.ts';
import { SCENARIOS } from '../data/scenarios.ts';
import { TREES } from '../data/dialogueTree.ts';
import { countRuleWords } from '../services/rules.ts';

const DIFFS = ['简单实习', '标准实训', '挑战督导'] as const;
const AI_MODES = [
  { key: 'rule', label: '规则模式' },
  { key: 'hybrid', label: '混合模式' },
  { key: 'ai', label: '全 AI 模式' },
] as const;

export default function SettingsPage() {
  const nav = useNavigate();
  const { account, records, logout } = useStore();
  const [s, setS] = useState<UserSettings>(() => loadSettingsLocal());
  const [msg, setMsg] = useState('');
  const ai = useAiStatus();
  const [usage, setUsage] = useState<AiHealth | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState('');
  const [baseInput, setBaseInput] = useState(() => getAiBase());

  useEffect(() => {
    void fetchUsage().then(setUsage);
  }, [ai.checkedAt]);

  function update<K extends keyof UserSettings>(k: K, v: UserSettings[K]) {
    const next = saveSettingsLocal({ [k]: v } as Partial<UserSettings>);
    setS(next);
    if (k === 'ai_enabled') setAiEnabled(v === true);
  }

  async function doSelftest() {
    setTesting(true);
    setTestResult('');
    try {
      const r = await selftest();
      setTestResult(
        r.ok
          ? `连通正常 · ${r.model} · ${r.ms}ms · 返回 ${JSON.stringify(r.sample || '').slice(0, 60)}`
          : `失败：${r.detail || '未知原因'}`,
      );
      await probeAi();
      setUsage(await fetchUsage());
    } finally {
      setTesting(false);
    }
  }

  function doExport() {
    if (records.length === 0) {
      setMsg('还没有训练记录可导出');
      return;
    }
    const mine = records.filter((r) => !account || r.nickname === account.nickname);
    if (mine.length === 0) {
      setMsg('当前账号还没有训练记录');
      return;
    }
    const rows = mine.map((r) => ({
      时间: new Date(r.createdAt).toLocaleString('zh-CN'),
      剧本: r.scriptName,
      原型: r.archetype,
      难度: r.difficulty,
      综合分: r.total,
      同感与倾听: r.scores.empathy,
      提问与对焦: r.scores.question,
      信息提供与建议: r.scores.advice,
      伦理原则: r.scores.ethics,
      过程完整性: r.scores.process,
      风险识别与转介: r.scores.risk,
      AI参与: r.aiUsed ? '是' : '否',
      无剧透: r.blindfold ? '是' : '否',
    }));
    downloadText(
      `叩门-训练记录-${account?.nickname ?? '我'}-${new Date().toISOString().slice(0, 10)}.csv`,
      exportCsv(account?.nickname ?? '', rows),
    );
    setMsg(`已导出 ${mine.length} 条记录`);
  }

  async function doPurge() {
    if (!confirm('确定清空当前账号的全部本地数据？\n\n训练记录、逐句点评、复盘与设置都会被删除，且无法恢复。账号本身会保留。')) return;
    await purgeLocal();
    setMsg('本地数据已清空，正在重新加载…');
    setTimeout(() => location.reload(), 800);
  }

  const nodeTotal = Object.values(TREES).reduce((n, t) => n + (Array.isArray(t) ? t.length : 0), 0);

  return (
    <div className="screen is-on">
      <div className="set-head">
        <div>
          <div className="k">设置 · Settings</div>
          <h2>训练偏好与数据</h2>
        </div>
        {msg && <div className="set-msg">{msg}</div>}
      </div>

      {/* ── 训练偏好 ── */}
      <section className="set-sec">
        <h3>训练偏好</h3>

        <div className="set-row">
          <div className="set-l">
            <b>默认难度</b>
            <span>每次进「服务对象」页的初始选项</span>
          </div>
          <div className="set-r">
            <div className="seg">
              {DIFFS.map((d) => (
                <button key={d} type="button" className="seg-opt"
                  aria-pressed={s.default_difficulty === d}
                  onClick={() => update('default_difficulty', d)}>{d}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>默认开启无剧透模式</b>
            <span>第一次训练不显示分数，专注在对话本身</span>
          </div>
          <div className="set-r">
            <button className="sw-btn" type="button" aria-pressed={s.blindfold_default}
              onClick={() => update('blindfold_default', !s.blindfold_default)}>
              <span className="sw" /><span>{s.blindfold_default ? '开' : '关'}</span>
            </button>
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>提交后自动进入结算页</b>
            <span>关闭后需要自己点导航标签</span>
          </div>
          <div className="set-r">
            <button className="sw-btn" type="button" aria-pressed={s.auto_settle}
              onClick={() => update('auto_settle', !s.auto_settle)}>
              <span className="sw" /><span>{s.auto_settle ? '开' : '关'}</span>
            </button>
          </div>
        </div>
      </section>

      {/* ── AI 与依据 ── */}
      <section className="set-sec">
        <h3>AI 与依据</h3>

        <div className="set-row">
          <div className="set-l">
            <b>启用 AI 增强</b>
            <span>
              当前状态：<b>{ai.label}</b>
              {ai.ready ? ` · ${ai.model} · 探测 ${ai.latencyMs}ms` : ` — ${ai.detail}`}
            </span>
          </div>
          <div className="set-r">
            <button className="sw-btn" type="button" aria-pressed={s.ai_enabled}
              onClick={() => update('ai_enabled', !s.ai_enabled)}>
              <span className="sw" /><span>{s.ai_enabled ? '开' : '关'}</span>
            </button>
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>默认 AI 参与度</b>
            <span>进训练页时的初始模式，可在训练页随时切换</span>
          </div>
          <div className="set-r">
            <div className="seg">
              {AI_MODES.map((m) => (
                <button key={m.key} type="button" className="seg-opt"
                  aria-pressed={(s.ai_mode ?? 'ai') === m.key}
                  onClick={() => update('ai_mode', m.key)}>{m.label}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="set-note">
          <b>模型：GLM-4.7-Flash（智谱开放平台）</b>，经本项目自带的 Node 服务（server/）同源转发，
          密钥不出现在前端产物里。该模型默认开启「深度推理」，本项目在请求中关闭 thinking，
          否则 token 会被思维链吃光、正文返回空。
          {ai.lastError ? <>　最近错误：<b>{ai.lastError}</b></> : null}
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>AI 服务地址</b>
            <span>留空 = 同源 /api。跨机部署时填 http://主机:8787</span>
          </div>
          <div className="set-r" style={{ display: 'flex', gap: 8 }}>
            <input
              value={baseInput}
              onChange={(e) => setBaseInput(e.target.value)}
              placeholder="（留空 = 同源）"
              style={{
                width: 190, padding: '7px 9px', fontSize: 12.5,
                border: '1px solid var(--rule)', background: 'transparent', color: 'inherit',
              }}
            />
            <button className="btn-ghost btn-sm" type="button"
              onClick={async () => {
                setAiBase(baseInput);
                await probeAi();
                setMsg(baseInput ? `AI 服务地址已设为 ${baseInput}` : 'AI 服务地址已恢复为同源 /api');
              }}>保存并检测</button>
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>连通性自检</b>
            <span>
              {usage?.ai?.configured === false
                ? '服务端未配置 GLM_API_KEY —— 请编辑 server/.env'
                : usage
                  ? `今日已调用 ${usage.usage?.calls ?? 0} 次 / 上限 ${usage.usage?.dailyCap ?? '—'}；成功 ${usage.usage?.ok ?? 0}、失败 ${usage.usage?.failed ?? 0}；累计 token ${(usage.usage?.tokensIn ?? 0) + (usage.usage?.tokensOut ?? 0)}`
                  : '未检测到服务 —— 请执行 npm run serve'}
            </span>
          </div>
          <div className="set-r">
            <button className="btn-primary btn-sm" type="button" onClick={doSelftest} disabled={testing}>
              {testing ? '检测中…' : '发一次真实请求'}
            </button>
          </div>
        </div>
        {testResult && <div className="set-note">{testResult}</div>}

        <div className="set-note">
          关闭后全部判定由本地 <b>{countRuleWords()} 条规则</b>完成，功能不缺。
          这是本作品的设计前提：<b>AI 不可用时训练流程必须照样跑通。</b>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>点评显示条款依据</b>
            <span>关闭后只给结论，不显示方法条款出处</span>
          </div>
          <div className="set-r">
            <button className="sw-btn" type="button" aria-pressed={s.show_basis}
              onClick={() => update('show_basis', !s.show_basis)}>
              <span className="sw" /><span>{s.show_basis ? '开' : '关'}</span>
            </button>
          </div>
        </div>
      </section>

      {/* ── 数据 ── */}
      <section className="set-sec">
        <h3>数据</h3>

        <div className="set-row">
          <div className="set-l">
            <b>导出训练记录</b>
            <span>
              共 <b>{records.length}</b> 条 · 导出为 CSV（Excel 可直接打开）
            </span>
          </div>
          <div className="set-r">
            <button className="btn-primary btn-sm" type="button" onClick={doExport}
              disabled={records.length === 0}>导出 CSV</button>
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>数据库状态</b>
            <span>
              {dbReady
                ? '已连接 · 数据会同步到云端，换设备也能看到'
                : '未配置 · 数据只存在这台设备上（不影响任何功能）'}
            </span>
          </div>
          <div className="set-r">
            <span className={'db-dot ' + (dbReady ? 'on' : 'off')} />
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>清空本地数据</b>
            <span>删除全部训练记录与设置，不可恢复</span>
          </div>
          <div className="set-r">
            <button className="btn-danger btn-sm" type="button" onClick={doPurge}>
              清空
            </button>
          </div>
        </div>

        <div className="set-row">
          <div className="set-l">
            <b>退出当前账号</b>
            <span>账号：<b>{account?.nickname}</b></span>
          </div>
          <div className="set-r">
            <button className="btn-ghost btn-sm" type="button"
              onClick={() => { logout(); nav('/login'); }}>退出</button>
          </div>
        </div>
      </section>

      {/* ── 内容规模 ── */}
      <section className="set-sec">
        <h3>本作品的内容规模</h3>
        <div className="set-stats">
          <div><b>{SCENARIOS.length}</b><span>位服务对象</span></div>
          <div><b>{nodeTotal}</b><span>个台词节点</span></div>
          <div><b>{SKILL_CARDS.length}</b><span>张技巧卡</span></div>
          <div><b>{ETHICS.length}</b><span>条伦理守则</span></div>
          <div><b>{countRuleWords()}</b><span>条判定规则</span></div>
          <div><b>6</b><span>维评分</span></div>
        </div>
        <div className="set-note">
          全部内容锚定
          <b>民政部《社会工作方法 个案工作》（公告第 426 号）</b>，
          每一条评分与守则都可追溯到具体条款。
        </div>
      </section>

      <div className="set-actions">
        <button className="btn-primary" type="button" onClick={() => nav('/cases')}>
          去训练 →
        </button>
        <button className="btn-ghost" type="button" onClick={() => nav('/about')}>
          关于与声明
        </button>
      </div>
    </div>
  );
}
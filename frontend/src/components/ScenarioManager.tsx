/**
 * 案例管理（教师端与管理端共用）
 *
 * 为什么做成共用组件：
 * 案例（服务对象）的新建/编辑是**同一件事**，只是权限不同——
 * 内置案例仅管理员可改，自建案例只有创建者与管理员可改。
 * 两端各写一套 UI 会立刻出现"字段不一样、提示不一样"的漂移，
 * 所以这里只做一套，权限差异由后端的 `editable` 标记驱动：
 * 不可编辑的行不渲染编辑/下架按钮，后端再兜一层 403。
 *
 * 接口用 `/api/v1/teacher/scenarios`：它允许教师与管理员，
 * 因此两端都能用同一份数据源。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import { ConfirmDialog, type ConfirmOptions } from './ConfirmDialog.tsx';
import { apiGet, apiSend } from '../lib/authClient.ts';

export interface ScenarioRow {
  id: string;
  name: string;
  age: number;
  gender: string;
  archetype: string;
  difficulty: number;
  difficulty_label: string;
  resistance: number;
  sensitive_tag: string | null;
  brief: string;
  initial_emotion: number;
  active: boolean;
  custom: boolean;
  created_by: string | null;
  owner_name: string | null;
  editable: boolean;
}

interface FormState {
  id: string;
  name: string;
  age: number;
  gender: string;
  archetype: string;
  difficulty: number;
  resistance: number;
  sensitive_tag: string;
  brief: string;
  initial_emotion: number;
  system_prompt: string;
  voice_low: string;
  voice_mid: string;
  voice_high: string;
}

const EMPTY: FormState = {
  id: '', name: '', age: 45, gender: '女', archetype: '', difficulty: 3,
  resistance: 3, sensitive_tag: '无', brief: '', initial_emotion: 45,
  system_prompt: '', voice_low: '', voice_mid: '', voice_high: '',
};

export function ScenarioManager({
  notify,
  onChanged,
}: {
  /** 统一的提示回调，交给宿主页面显示（两端提示样式一致） */
  notify: (msg: string, ok?: boolean) => void;
  /** 数据变化后的回调，宿主可据此刷新其它依赖案例的列表 */
  onChanged?: () => void;
}) {
  const [rows, setRows] = useState<ScenarioRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmOptions | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await apiGet<{ items: ScenarioRow[] }>('/api/v1/teacher/scenarios');
    setRows(r?.items ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = useMemo(() => {
    const mine = rows.filter((r) => r.custom && r.editable).length;
    const builtin = rows.filter((r) => !r.custom).length;
    return { mine, builtin, total: rows.length };
  }, [rows]);

  async function save() {
    if (!form.id.trim() || !form.name.trim()) {
      notify('案例需要 ID 与姓名', false);
      return;
    }
    if (!form.brief.trim()) {
      notify('请填写主诉/背景，训练页要用它交代情境', false);
      return;
    }
    if (!form.system_prompt.trim()) {
      notify('请填写角色设定（system_prompt），AI 扮演要用它', false);
      return;
    }
    const r = await apiSend('POST', '/api/v1/teacher/scenarios', form);
    notify(r.ok ? `案例 ${form.id} 已保存` : r.msg, r.ok);
    if (r.ok) {
      setForm(EMPTY);
      setEditing(false);
      await load();
      onChanged?.();
    }
  }

  function edit(row: ScenarioRow) {
    setForm({
      id: row.id,
      name: row.name,
      age: row.age,
      gender: row.gender,
      archetype: row.archetype,
      difficulty: row.difficulty,
      resistance: row.resistance,
      sensitive_tag: row.sensitive_tag ?? '无',
      brief: row.brief,
      initial_emotion: row.initial_emotion,
      system_prompt: '',
      voice_low: '',
      voice_mid: '',
      voice_high: '',
    });
    setEditing(true);
  }

  function archive(row: ScenarioRow) {
    setConfirm({
      title: '下架案例',
      message: `案例 ${row.id}「${row.name}」将不再出现在选角列表，`
        + '历史训练记录仍可查看。确定下架？',
      confirmLabel: '下架',
      danger: true,
      onConfirm: async () => {
        const r = await apiSend('DELETE', `/api/v1/teacher/scenarios/${row.id}`);
        notify(r.ok ? `案例 ${row.id} 已下架` : r.msg, r.ok);
        if (r.ok) {
          await load();
          onChanged?.();
        }
      },
    });
  }

  return (
    <>
      <div className="wb-panel">
        <div className="wb-panel-h">
          <span>{editing ? `编辑案例 ${form.id}` : '新建案例'}</span>
          <span className="hint">
            内置 {stats.builtin} 个 · 我可编辑 {stats.mine} 个
          </span>
        </div>

        <div className="wb-form">
          <input
            className="wb-input" style={{ width: 110 }}
            placeholder="ID（X-01）" value={form.id}
            disabled={editing}
            onChange={(e) => setForm({ ...form, id: e.target.value })}
          />
          <input
            className="wb-input" style={{ width: 110 }}
            placeholder="称呼（李叔）" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className="wb-input" style={{ width: 72 }} type="number"
            placeholder="年龄" value={form.age}
            onChange={(e) => setForm({ ...form, age: Number(e.target.value) })}
          />
          <select
            className="wb-input" style={{ width: 70 }} value={form.gender}
            onChange={(e) => setForm({ ...form, gender: e.target.value })}
          >
            <option value="女">女</option>
            <option value="男">男</option>
          </select>
          <input
            className="wb-input" style={{ width: 150 }}
            placeholder="类型（空巢老人）" value={form.archetype}
            onChange={(e) => setForm({ ...form, archetype: e.target.value })}
          />
          <label className="hint" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            难度
            <select
              className="wb-input" style={{ width: 64 }} value={form.difficulty}
              onChange={(e) => setForm({ ...form, difficulty: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="hint" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            阻抗
            <select
              className="wb-input" style={{ width: 64 }} value={form.resistance}
              onChange={(e) => setForm({ ...form, resistance: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button
            className="btn-primary" type="button" onClick={() => void save()}
            style={{ padding: '9px 18px' }}
          >
            {editing ? '保存修改' : '保存'}
          </button>
          {editing && (
            <button
              className="btn-ghost" type="button"
              onClick={() => { setForm(EMPTY); setEditing(false); }}
              style={{ padding: '9px 14px' }}
            >
              取消
            </button>
          )}
        </div>

        <div className="wb-form" style={{ alignItems: 'flex-start' }}>
          <textarea
            className="wb-input" rows={2}
            style={{ flex: 1, minWidth: 260, resize: 'vertical' }}
            placeholder="主诉 / 背景（训练页顶部会展示，交代情境与核心诉求）"
            value={form.brief}
            onChange={(e) => setForm({ ...form, brief: e.target.value })}
          />
        </div>
        <div className="wb-form" style={{ alignItems: 'flex-start' }}>
          <textarea
            className="wb-input" rows={3}
            style={{ flex: 1, minWidth: 260, resize: 'vertical' }}
            placeholder="角色设定（system_prompt）：身份、处境、说话方式、敏感点、禁止事项。AI 扮演该角色时按此生成台词。"
            value={form.system_prompt}
            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
          />
        </div>
        <div className="wb-form">
          <input
            className="wb-input" style={{ width: 190 }}
            placeholder="低情绪台词（可选，AI 未配时的兜底）"
            value={form.voice_low}
            onChange={(e) => setForm({ ...form, voice_low: e.target.value })}
          />
          <input
            className="wb-input" style={{ width: 150 }}
            placeholder="中情绪台词"
            value={form.voice_mid}
            onChange={(e) => setForm({ ...form, voice_mid: e.target.value })}
          />
          <input
            className="wb-input" style={{ width: 190 }}
            placeholder="高情绪台词"
            value={form.voice_high}
            onChange={(e) => setForm({ ...form, voice_high: e.target.value })}
          />
        </div>
      </div>

      <div className="wb-panel">
        <div className="wb-panel-h">
          <span>案例列表</span>
          <span className="hint">
            共 {stats.total} 个 · 内置案例仅管理员可改
          </span>
        </div>
        {loading && <div className="wb-empty">加载中…</div>}
        {!loading && rows.length === 0 && <div className="wb-empty">还没有案例</div>}
        {!loading && rows.map((s) => (
          <div key={s.id} className="wb-row">
            <span className="mono" style={{ width: 52 }}>{s.id}</span>
            <span className="name">{s.name}</span>
            <span className="mono">{s.archetype}</span>
            <span className="spacer" />
            <span className="tag">{s.difficulty_label}</span>
            <span className="tag">{s.custom ? (s.owner_name ?? '自建') : '内置'}</span>
            <span className={`tag ${s.active ? 'ok' : 'warn'}`}>
              {s.active ? '在架' : '已下架'}
            </span>
            {s.editable ? (
              <>
                <button
                  className="btn-ghost" type="button" onClick={() => edit(s)}
                  style={{ padding: '5px 12px', fontSize: 12 }}
                >
                  编辑
                </button>
                {s.active && (
                  <button
                    className="btn-ghost" type="button" onClick={() => archive(s)}
                    style={{ padding: '5px 12px', fontSize: 12 }}
                  >
                    下架
                  </button>
                )}
              </>
            ) : (
              <span className="hint" style={{ fontSize: 11 }}>只读</span>
            )}
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        options={confirm}
        onClose={() => setConfirm(null)}
      />
    </>
  );
}

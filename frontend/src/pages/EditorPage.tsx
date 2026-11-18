/**
 * 10 剧本编辑器 —— 让使用者自己加角色
 *
 * 产出写入 localStorage 的 custom_scripts，
 * 服务对象页会把它们与内置 12 位角色合并展示。
 *
 * 设计约束：
 *  · 字段与 case_scripts 对齐，便于将来同步到云端
 *  · systemPrompt 用「结构化模板」生成，不要求用户懂提示词工程
 *  · 无台词树时用通用兜底（已在 getTree 里处理，不会串到别人台词）
 */
import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadSettingsLocal, saveSettingsLocal } from '../lib/db.ts';
import { SCENARIOS } from '../data/scenarios.ts';
import { buildScriptTree } from '../data/scriptTreeGen.ts';

export interface CustomScript {
  id: string;
  name: string;
  age: number;
  gender: '男' | '女';
  archetype: string;
  difficulty: number;
  sensitiveTag: string;
  brief: string;
  resistance: string;
  systemPrompt: string;
  /** ★ 按阻抗形态生成的台词树，getTree 会读它 */
  tree: ReturnType<typeof buildScriptTree>;
  createdAt: number;
}

const RESISTANCES = [
  ['polite-avoidance', '礼貌回避', '用"还行""没事"挡住真实感受'],
  ['complaint-first', '抱怨优先', '开口先讲困难，把话题引向别人'],
  ['silent-refusal', '沉默拒绝', '极短发，只用"嗯""不知道"'],
  ['dignity-first', '尊严优先', '最忌同情与怜悯，要平等'],
  ['deny-then-crack', '先否认后崩溃', '反复否认，被戳破才崩溃'],
  ['caregiver-burnout', '照护耗竭', '怕添麻烦，一直说"还行"'],
  ['stigma-avoid', '污名回避', '把每次谈话都理解为审查'],
  ['minimizer', '最小化', '先归因于作息，末段才松动'],
] as const;

const ARCHETYPES = [
  '空巢老人', '单亲母亲', '厌学青少年', '肢体残障', '失业中年', '家暴受暴者',
  '失能老人家庭照护者', '移民新居民', '社区矫正对象', '退役军人', '在校心理求助者',
  '独居青年', '丧偶老人', '外来务工者', '再婚家庭',
];

const EMPTY = {
  name: '',
  age: 60,
  gender: '女' as '男' | '女',
  archetype: '独居老人',
  difficulty: 3,
  sensitiveTag: '无',
  brief: '',
  resistance: 'polite-avoidance',
};

/** 按人设生成结构化 system prompt */
function buildPrompt(f: typeof EMPTY & { name: string }): string {
  const r = RESISTANCES.find((x) => x[0] === f.resistance);
  return `你扮演${f.name}，${f.age}岁${f.archetype}。

【背景】
${f.brief || '（待补充）'}

【阻抗形态】
${r ? `${r[1]} —— ${r[2]}` : '未指定'}

【情绪三档说话风格】
- 情绪 ≤29（回避）：话最少，用最短的句子，能不答就不答
- 情绪 30-69（平实）：愿意谈具体事实，但不下判断
- 情绪 ≥70（打开）：愿意讲细节，语气变软

【铁律】
1. 只输出这个角色说的一句话，不超过 25 字。
2. 不写旁白、不写动作、不加引号、不写说话人标签。
3. 保持口语化，避免书面语和成语。
4. 不输出任何 meta 标记。
5. 严守专业边界，不替对方做决定、不评判、不给建议。`;
}

export default function EditorPage() {
  const nav = useNavigate();
  const [list, setList] = useState<CustomScript[]>(
    () => loadSettingsLocal().custom_scripts as CustomScript[],
  );
  const [f, setF] = useState(EMPTY);
  const [preview, setPreview] = useState('');
  const [err, setErr] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  function save() {
    if (!f.name.trim()) { setErr('请填写角色姓名'); return; }
    if (!f.brief.trim()) { setErr('请填写背景简介（AI 扮演需要）'); return; }

    const dup = list.some((x) => x.name === f.name.trim());
    if (dup) { setErr(`「${f.name.trim()}」已存在`); return; }

    // id 用 X- 前缀，与内置的 W/L/C 等区分
    const n = 60 + list.length;
    const item: CustomScript = {
      id: 'X-' + String(n).padStart(2, '0'),
      name: f.name.trim(),
      age: Number(f.age) || 60,
      gender: f.gender,
      archetype: f.archetype,
      difficulty: Number(f.difficulty) || 3,
      sensitiveTag: f.sensitiveTag,
      brief: f.brief.trim(),
      resistance: f.resistance,
      systemPrompt: buildPrompt({ ...f, name: f.name.trim() }),
      tree: buildScriptTree(f.resistance),
      createdAt: Date.now(),
    };
    const next = [...list, item];
    setList(next);
    saveSettingsLocal({ custom_scripts: next });
    setF(EMPTY);
    setErr('');
    setPreview('');
  }

  function remove(id: string) {
    if (!confirm('确定删除这个自定义角色？')) return;
    const next = list.filter((x) => x.id !== id);
    setList(next);
    saveSettingsLocal({ custom_scripts: next });
  }

  async function importAll(file: File) {
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const incoming: CustomScript[] = Array.isArray(data)
        ? data
        : Array.isArray(data?.custom_scripts) ? data.custom_scripts : [];
      if (incoming.length === 0) {
        setErr('文件里没有找到角色数据');
        return;
      }
      if (!confirm(`将导入 ${incoming.length} 个角色，与现有 ${list.length} 个合并（同 id 会覆盖），继续？`)) return;

      const map = new Map<string, CustomScript>();
      list.forEach((x) => map.set(x.id, x));
      let skipped = 0;
      incoming.forEach((x) => {
        if (!x?.id || !x?.name) { skipped++; return; }
        // 补齐缺省字段，避免旧文件缺键
        map.set(x.id, {
          id: String(x.id), name: String(x.name),
          age: Number(x.age) || 60,
          gender: x.gender === '男' ? '男' : '女',
          archetype: String(x.archetype ?? '自定义'),
          difficulty: Number(x.difficulty) || 3,
          sensitiveTag: String(x.sensitiveTag ?? '无'),
          brief: String(x.brief ?? ''),
          resistance: String(x.resistance ?? 'polite-avoidance'),
          systemPrompt: String(x.systemPrompt ?? buildPrompt({
            name: String(x.name), age: Number(x.age) || 60,
            gender: '女', archetype: String(x.archetype ?? '自定义'),
            difficulty: 3, sensitiveTag: '无', brief: String(x.brief ?? ''),
            resistance: String(x.resistance ?? 'polite-avoidance'),
          })),
          tree: Array.isArray((x as { tree?: unknown }).tree) && (x as { tree: unknown[] }).tree.length > 0
            ? ((x as { tree: unknown[] }).tree as CustomScript['tree'])
            : buildScriptTree(String(x.resistance ?? 'polite-avoidance')),
          createdAt: Number(x.createdAt) || Date.now(),
        });
      });
      const next = [...map.values()];
      setList(next);
      saveSettingsLocal({ custom_scripts: next });
      setErr(skipped > 0
        ? `已导入 ${next.length} 个角色（跳过 ${skipped} 条格式不对的）`
        : `已导入 ${incoming.length} 个角色`);
    } catch (e) {
      setErr('导入失败：' + (e instanceof Error ? e.message : '文件格式不对'));
    }
  }

  function exportAll() {
    if (list.length === 0) return;
    const blob = new Blob([JSON.stringify(list, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `叩门-自定义剧本-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return (
    <div className="screen is-on">
      <div className="ed-head">
        <div>
          <div className="k">剧本编辑器 · Case Editor</div>
          <h2>加一个你自己的服务对象</h2>
          <p>
            内置 {SCENARIOS.length} 位角色覆盖 9 种阻抗形态。
            遇到真实案例时，可以在这里加一个 —— 填完立刻能练。
          </p>
        </div>
        <div className="ed-head-btns">
          <input ref={fileRef} type="file" accept="application/json,.json"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importAll(f);
              e.target.value = '';
            }} />
          <button className="btn-ghost btn-sm" type="button"
            onClick={() => fileRef.current?.click()}>
            导入 JSON
          </button>
          {list.length > 0 && (
            <button className="btn-ghost btn-sm" type="button" onClick={exportAll}>
              导出 JSON
            </button>
          )}
        </div>
      </div>

      <div className="ed-cols">
        {/* ── 表单 ── */}
        <section className="ed-form">
          <h3>基本信息</h3>

          <div className="ed-grid">
            <label className="field">
              <span>姓名 *</span>
              <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
                placeholder="例如：老郑" />
            </label>
            <label className="field">
              <span>年龄</span>
              <input type="number" min={12} max={95} value={f.age}
                onChange={(e) => setF({ ...f, age: +e.target.value })} />
            </label>
            <label className="field">
              <span>性别</span>
              <div className="seg seg-sm">
                {(['女', '男'] as const).map((g) => (
                  <button key={g} type="button" className="seg-opt"
                    aria-pressed={f.gender === g}
                    onClick={() => setF({ ...f, gender: g })}>{g}</button>
                ))}
              </div>
            </label>
            <label className="field">
              <span>难度（1-5）</span>
              <div className="seg seg-sm">
                {[1, 2, 3, 4, 5].map((d) => (
                  <button key={d} type="button" className="seg-opt"
                    aria-pressed={f.difficulty === d}
                    onClick={() => setF({ ...f, difficulty: d })}>{d}</button>
                ))}
              </div>
            </label>
          </div>

          <div className="field">
            <span>身份原型（点选或自己写）</span>
            <input value={f.archetype}
              onChange={(e) => setF({ ...f, archetype: e.target.value })}
              placeholder="例如：货车司机" />
            <div className="chips">
              {ARCHETYPES.map((a) => (
                <button key={a} type="button"
                  className={'chip' + (f.archetype === a ? ' on' : '')}
                  onClick={() => setF({ ...f, archetype: a })}>{a}</button>
              ))}
            </div>
          </div>

          <label className="field">
            <span>阻抗形态</span>
            <div className="res-list">
              {RESISTANCES.map(([id, name, desc]) => (
                <button key={id} type="button"
                  className={'res-opt' + (f.resistance === id ? ' on' : '')}
                  onClick={() => setF({ ...f, resistance: id })}>
                  <b>{name}</b><span>{desc}</span>
                </button>
              ))}
            </div>
          </label>

          <label className="field">
            <span>背景简介 *（AI 扮演的依据）</span>
            <textarea value={f.brief} rows={4}
              onChange={(e) => setF({ ...f, brief: e.target.value })}
              placeholder="例如：老郑，58岁，货车司机，妻子查出尿毒症需要透析，每月治疗费压得喘不过气。来了两次都说'挺好的'。" />
          </label>

          <label className="field">
            <span>敏感议题标签</span>
            <div className="seg seg-sm">
              {['无', '含轻度无望感表达', '含敏感议题'].map((t) => (
                <button key={t} type="button" className="seg-opt"
                  aria-pressed={f.sensitiveTag === t}
                  onClick={() => setF({ ...f, sensitiveTag: t })}>{t}</button>
              ))}
            </div>
          </label>

          {err && <div className="ed-err">{err}</div>}

          <div className="ed-btns">
            <button className="btn-primary" type="button" onClick={save}>保存并可训练</button>
            <button className="btn-ghost" type="button" onClick={() => setPreview(buildPrompt({ ...f, name: f.name || '（未命名）' }))}>
              预览 system prompt
            </button>
          </div>

          {preview && (
            <pre className="ed-preview">{preview}</pre>
          )}
        </section>

        {/* ── 已创建 ── */}
        <section className="ed-list">
          <h3>已创建 {list.length ? `（${list.length}）` : ''}</h3>

          {list.length === 0 && (
            <div className="kb-empty">
              还没有自定义角色。填完左边的表单点「保存并可训练」，
              它会出现在「服务对象」页的列表末尾。
            </div>
          )}

          {list.map((x) => (
            <div className="ed-item" key={x.id}>
              <div className="edi-top">
                <span className="edi-id">{x.id}</span>
                <span className="edi-nm">{x.name}</span>
                <span className="edi-meta">{x.age} 岁 · {x.gender} · {x.archetype}</span>
                <span className="edi-d">{x.difficulty}/5</span>
              </div>
              <p className="edi-brief">{x.brief}</p>
              <div className="edi-foot">
                <span className="tag">{RESISTANCES.find((r) => r[0] === x.resistance)?.[1] ?? x.resistance}</span>
                {x.sensitiveTag !== '无' && <span className="tag proof">{x.sensitiveTag}</span>}
                <button className="linkd" type="button" onClick={() => nav('/training/' + x.id)}>
                  去训练 →
                </button>
                <button className="linkd danger" type="button" onClick={() => remove(x.id)}>
                  删除
                </button>
              </div>
            </div>
          ))}

          {list.length > 0 && (
            <div className="ed-note">
              自定义角色使用<b>通用兜底台词</b>（不与内置角色混用），
              台词由 AI 按人设实时生成。若要配置固定台词树，
              需要在 <code>src/data/dialogueTreeExtra.ts</code> 中按同样的结构补一份。
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
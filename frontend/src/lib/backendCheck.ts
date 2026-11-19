/**
 * 后端自检 —— 平台接完数据库与 AI 后跑一次，知道还缺什么
 *
 * 用法：
 *   ① 先在项目根建 .env.local，填好两个变量
 *   ② node --experimental-strip-types src/lib/backendCheck.ts
 *
 * 退出码：0 = 全部通过（可直接提交）；1 = 有 FAIL
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..');

let pass = 0, fail = 0, warn = 0;
const ok = (m: string) => { pass++; console.log('  \x1b[32mPASS\x1b[0m  ' + m); };
const no = (m: string, fix?: string) => {
  fail++; console.log('  \x1b[31mFAIL\x1b[0m  ' + m);
  if (fix) console.log('        → ' + fix);
};
const wa = (m: string, fix?: string) => {
  warn++; console.log('  \x1b[33mWARN\x1b[0m  ' + m);
  if (fix) console.log('        → ' + fix);
};

/* ══════════ 1. 环境变量 ══════════ */
console.log('\n\x1b[1m[1] 环境配置\x1b[0m');
const envPath = path.join(ROOT, '.env.local');
const env: Record<string, string> = {};
if (!fs.existsSync(envPath)) {
  no('.env.local 不存在', 'cp .env.example .env.local 然后填入真实值');
} else {
  ok('.env.local 存在');
  const text = fs.readFileSync(envPath, 'utf8');
  for (const line of text.split('\n')) {
    const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.+?)\s*$/);
    if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
  const url = env.VITE_SUPABASE_URL ?? '';
  const key = env.VITE_SUPABASE_ANON_KEY ?? '';
  if (!url || url.includes('placeholder')) {
    no('VITE_SUPABASE_URL 未填真实值', '从 Supabase 控制台 → Project Settings → API 复制');
  } else if (!url.startsWith('https://')) {
    no('VITE_SUPABASE_URL 格式不对', '应该以 https:// 开头');
  } else ok('VITE_SUPABASE_URL 已配置');
  if (!key || key.includes('placeholder') || key.length < 20) {
    no('VITE_SUPABASE_ANON_KEY 未填真实值', '同上，anon key 通常 40+ 字符');
  } else ok('VITE_SUPABASE_ANON_KEY 已配置');
}

/* ══════════ 2. 数据库连通 + 表 ══════════ */
console.log('\n\x1b[1m[2] 数据库\x1b[0m');
if (env.VITE_SUPABASE_URL?.startsWith('https://')
    && !env.VITE_SUPABASE_URL.includes('placeholder')) {
  const tables = [
    'case_scripts', 'training_records', 'training_details',
    'proficiency', 'achievement', 'session_record', 'user_settings',
  ];
  const views = ['v_user_stats', 'v_heatmap', 'v_script_progress', 'v_dimension_avg'];
  const url = env.VITE_SUPABASE_URL!;
  const anon = env.VITE_SUPABASE_ANON_KEY!;

  for (const t of [...tables, ...views]) {
    try {
      const res = await fetch(`${url}/rest/v1/${t}?select=*&limit=1`, {
        headers: { apikey: anon, Authorization: `Bearer ${anon}` },
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) ok(`${t} 可查询`);
      else if (res.status === 401 || res.status === 403) {
        no(`${t} 存在但 RLS 拒绝访问`, '检查该表是否 enable row level security 并建了 policy');
      } else {
        no(`${t} 查询失败（HTTP ${res.status}）`, '表可能没建，先跑 supabase/migrations/*.sql');
      }
    } catch {
      no(`${t} 请求失败`, '检查网络或 URL 是否正确');
    }
  }
} else {
  wa('跳过数据库连通性检查', '填好 .env.local 再跑一次');
}

/* ══════════ 3. AI 链路 ══════════ */
console.log('\n\x1b[1m[3] AI 技能\x1b[0m');
const aiFn = path.join(ROOT, 'supabase/functions/wenxin-text-generation/index.ts');
if (!fs.existsSync(aiFn)) {
  no('Edge Function 文件不存在');
} else {
  const src = fs.readFileSync(aiFn, 'utf8');
  for (const fn of ['classifyIntent', 'actAsPersona', 'gradeStage', 'generateDebrief']) {
    if (src.includes(`function ${fn}`)) ok(`链路 ${fn} 已实现`);
    else no(`链路 ${fn} 缺失`);
  }
  if (src.includes('TIMEOUT_MS = 8000')) ok('超时 8 秒（铁律 3）');
  else wa('未找到 8 秒超时设置', 'AI 调用必须有超时，否则会卡住界面');
  // ★ 只看真实代码，剥掉注释再查；同时检查 fetch 是否在循环里
  const codeOnly = src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .split('Deno.serve')[0] ?? '';
  const inLoop = /\b(for|while)\s*\([^)]*\)[\s\S]{0,400}?fetch\s*\(/.test(codeOnly);
  const retryCall = /\bretry\s*[:(]|\bretryAfter\b/.test(codeOnly);
  if (inLoop || retryCall) {
    no('检测到重试逻辑', '平台单次 0.2 秒点，重试等于双倍烧');
  } else {
    ok('无重试逻辑（铁律 1）');
  }
}
console.log('  \x1b[36m注\x1b[0m  部署到平台时，把上面的 Edge Function 换成'
  + '「技能中心」的文本生成技能即可，前端一行不用改。');

/* ══════════ 4. 前端降级可用 ══════════ */
console.log('\n\x1b[1m[4] 无后端时能否跑通\x1b[0m');
const { matchLocalRules } = await import('../services/rules.ts');
const { generateReply } = await import('../services/dialogueEngine.ts');
const { getScenario } = await import('../data/scenarios.ts');
const sc = getScenario('W-01');
try {
  const m = matchLocalRules('您应该多出去走走');
  ok(`规则引擎可用（命中「${m.intent}」）`);
  const r = generateReply(sc!, 1, 45, '您应该多出去走走', m);
  ok(`台词生成可用：${r.text}`);
} catch (e) {
  no('规则引擎异常：' + (e instanceof Error ? e.message : String(e)));
}

/* ══════════ 汇总 ══════════ */
console.log('\n' + '═'.repeat(52));
const total = pass + fail + warn;
console.log(`通过 ${pass} / ${total} ` + (fail ? `\x1b[31m失败 ${fail}\x1b[0m` : '\x1b[32m全部通过\x1b[0m')
  + (warn ? ` 警告 ${warn}` : ''));
if (fail) {
  console.log('\n有必失败项，暂时不要提交。按上面的 → 提示逐条修。');
  process.exit(1);
}
if (warn) {
  console.log('\n警告项不影响提交（降级仍可用），但补上更好。');
}
console.log('\n下一步：把 docs/平台搭建/后端对接说明.md 发给平台搭建方。');
/**
 * AboutPage —— 三层架构 + 依据表 + 危机资源
 *
 * 结构与 class 名完全沿用 docs/预览/叩门-设计示例.html，视觉零改动。
 * 逻辑接在 src/services 与 src/hooks 上。
 *
 * ★ 本页所有数字都从代码常量现算，不在文案里写死：
 *   规则词表、剧本 / 节点 / 技巧卡 / 伦理守则数量都随内容层自动变。
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { SCENARIOS } from '../data/scenarios.ts';
import { SKILL_CARDS, ETHICS } from '../data/knowledge.ts';
import { TREES } from '../data/dialogueTree.ts';
import { countRuleWords } from '../services/rules.ts';
import { DIMENSIONS } from '../services/scoring.ts';

/* ── 页面数字：一律从代码常量算 ─────────────────────── */
const RULE_WORDS = countRuleWords(); // 关键词规则总条数（随 rules.ts 自动变）
const SCENARIO_COUNT = SCENARIOS.length; // 剧本数
const NODE_COUNT = Object.values(TREES).reduce((s, t) => s + t.length, 0); // 对话节点合计
const CARD_COUNT = SKILL_CARDS.length; // 面谈技巧卡
const ETHICS_CODES = ETHICS.filter((e) => e.code !== '—').length; // 国标条款
const ETHICS_DISCLAIMERS = ETHICS.length - ETHICS_CODES; // 工具边界声明
const DIMENSION_COUNT = DIMENSIONS.length; // 评分维度

/* AI 侧如实标注：模型名与服务端每日上限（server/.env 的 GLM_DAILY_CAP） */
const AI_MODEL = 'GLM-4.7-Flash';
const AI_DAILY_CAP = 800;

export default function AboutPage() {
  const nav = useNavigate();
  return (
    <div className="screen is-on">
  
    <div className="about-head">
      <div className="k">关于与声明 · About & Disclaimer</div>
      <h2>叩门是什么，不是什么</h2>
    </div>
  
    <div className="about-grid">
      <div className="ablock yes">
        <div className="k">它是什么</div>
        <ul>
          <li>一个<b>沟通训练工具</b>——让你在没有真实服务对象的情况下反复练习个案面谈</li>
          <li>{DIMENSION_COUNT} 维评分全部锚定<b>民政部《社会工作方法 个案工作》（公告第 426 号）</b>条款，每条判定都可溯源到具体规范号</li>
          <li>规则引擎与模型<b>并行</b>——关掉 AI 也能跑通全流程，评分依然可复算</li>
          <li>{SCENARIO_COUNT} 个剧本覆盖<b>六种阻抗形态</b>（客气回避 / 情绪拉同盟 / 高冷淡漠 / 对同情敏感 / 逞强否认 / 否认与反复淡化），每种配一条可判定的应对规则</li>
        </ul>
      </div>
      <div className="ablock no">
        <div className="k">它不是什么</div>
        <ul>
          <li><b>不是真实咨询工具</b>——不提供心理诊断、危机干预、法律或医疗建议</li>
          <li><b>不做安全评估</b>，不承担危机处理职能</li>
          <li>不是<b>录用评价系统</b>——训练的是你的面谈能力，不是给人打分定性</li>
          <li>阿珍剧本<b>不呈现任何暴力细节</b>，只做沟通层面的演练</li>
        </ul>
      </div>
    </div>
  
    <div className="about-sec">
      <table className="spec">
        <caption>AI 技术栈 · 三层架构与降级路径</caption>
        <tbody>
          <tr>
            <th>语义判别层</th>
            <td>{AI_MODEL}（经项目自带的 Node 服务转发，密钥只存在服务端）：① 长尾意图分类　② AI 实时扮演服务对象　③ 六维语义评分（与规则底分按 4:6 融合）　④ 复盘生成</td>
            <td className="src2">关闭 AI 或未配置密钥 → 全部功能仍可用</td>
          </tr>
          <tr><th>规则层</th><td>{RULE_WORDS} 条关键词规则 + 对话树状态机 + 危机硬拦截：六维判定、情绪值、阶段推进</td><td className="src">零延迟兜底，始终本地运行</td></tr>
          <tr><th>呈现层</th><td>{SCENARIO_COUNT} 个剧本 {NODE_COUNT} 个对话节点 + 台词变体 + {CARD_COUNT} 张知识卡，全部预置</td><td className="src">零调用</td></tr>
        </tbody>
      </table>
      <p className="note"><b>综合分 = 规则底分 × 0.4 + AI 语义评分 × 0.6。</b>模型不可用、或用户主动关闭 AI 时，规则底分仍能给出有专业依据的分数——这是本产品的确定性保障层设计。</p>
    </div>
  
    <div className="about-sec">
      <table className="spec">
        <caption>六维评分依据 · 每维可查条款出处</caption>
        <tbody>
          <tr><th>同感与倾听 25</th><td>积极倾听、专注、鼓励、同感</td><td className="src">公告第 426 号 · 6.1.1</td></tr>
          <tr><th>提问与对焦 20</th><td>提问、澄清、对焦、摘要</td><td className="src">公告第 426 号 · 6.1.2</td></tr>
          <tr><th>信息提供与建议 15</th><td>信息提供、自我披露、建议、忠告、对质</td><td className="src">公告第 426 号 · 6.1.3</td></tr>
          <tr><th>伦理原则 20</th><td>接纳、非评判、自决、保密</td><td className="src">公告第 426 号 · 4.2.4–4.2.7</td></tr>
          <tr><th>过程完整性 10</th><td>接案 → 预估 → 计划 → 介入 → 评估 → 结案</td><td className="src">公告第 426 号 · 6.1</td></tr>
          <tr><th>风险识别与转介 10</th><td>转介规范：征询意见 → 提供选项 → 协助联系 → 定期回访</td><td className="src">公告第 426 号 · 6.8.3</td></tr>
        </tbody>
      </table>
      <p className="note"><b>民政部《社会工作方法 个案工作》（公告第 426 号）</b>：六个维度的命名与权重均依据该标准，非自拟。</p>
    </div>
  
    <div className="about-sec">
      <table className="spec">
        <caption>数据来源与隐私</caption>
        <tbody>
          <tr><th>剧本内容</th><td>{SCENARIO_COUNT} 个服务对象原型为<b>虚构教学案例</b>，参考公开案例改编，不含任何真实个案例材</td><td className="src">人工编写</td></tr>
          <tr><th>知识卡</th><td>{CARD_COUNT} 张面谈技巧卡 + {ETHICS_CODES} 条伦理守则（另 {ETHICS_DISCLAIMERS} 条工具边界声明），每条标注国标出处</td><td className="src">人工整理</td></tr>
          <tr><th>训练记录</th><td>仅存储<b>六维分数与时间戳</b>，用于生成成长曲线</td><td className="src">本地数据库</td></tr>
          <tr><th>不采集</th><td>不采集真实姓名、联系方式、身份信息，不上传任何对话内容</td><td className="src2">隐私承诺</td></tr>
          <tr><th>AI 调用</th><td>服务端每日调用上限 <b>{AI_DAILY_CAP} 次</b>；关掉 AI 后全部功能仍可用</td><td className="src">成本控制</td></tr>
        </tbody>
      </table>
    </div>
  
    <div className="danger-zone">
      <div className="k" style={{'fontFamily':'var(--mono)','fontSize':'10px','letterSpacing':'.18em','textTransform':'uppercase','paddingBottom':'8px','borderBottom':'1px solid #E8C4BC','marginBottom':'var(--s4)'}}>危机资源 · 如果你或身边的人正处于危机中</div>
      <p className="hot">12356　<span>全国统一心理援助热线 · 24 小时 · 免费 · 精神科医师与心理治疗师接听</span></p>
      <p className="hot warn">110　<span>报警</span>　·　120　<span>急救</span></p>
      <p className="cite">12356 依据《国家卫生健康委关于应用"12356"全国统一心理援助热线电话号码的通知》（国卫医政函〔2024〕259 号），已与 110 / 119 / 120 建立联动机制。<br />机构内部支持渠道（实习督导 / 心理健康教育与咨询中心）请在使用前自行填写，此处不预置未经核实的号码。</p>
    </div>
  
    <div className="colophon">
      <span>叩门 · 社工个案面谈 AI 陪练舱</span>
      <span>视觉方向：杂志编辑 / 校样</span>
      <span>Built with React + Node.js</span>
    </div>
  
          <div style={{ marginTop: 32, paddingTop: 22, borderTop: "1px solid var(--rule)" }}>
        <button className="btn-primary" type="button" onClick={() => nav('/cases')}>
          开始第一次训练
        </button>
      </div>
</div>
  );
}

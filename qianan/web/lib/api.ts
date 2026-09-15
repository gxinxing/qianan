import { getAccessToken } from "./cloudbase";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8001";

/** 包装 fetch：自动带上 CloudBase 登录态的 access_token，供后端多租户隔离。 */
const _nativeFetch: typeof fetch =
  typeof window !== "undefined" && window.fetch
    ? window.fetch.bind(window)
    : (function () {
        return undefined;
      } as unknown as typeof fetch);

/** BYOK：访客自带的百炼 Key 存在 localStorage，随每个请求带给后端。
 *  服务端预置额度可用时不需要填；填了就优先用访客自己的额度。 */
export const BYOK_STORAGE_KEY = "qianan_byok_key";
const DASHSCOPE_STORAGE_KEY = "qianan_byok_dashscope_key";

export function getByokKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(BYOK_STORAGE_KEY) || "";
}

export function getByokDashscopeKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(DASHSCOPE_STORAGE_KEY) || "";
}

export async function qfetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || undefined);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // BYOK：带上了就覆盖服务端预置额度（后端用 ContextVar 按请求隔离，并发安全）
  const byok = getByokKey();
  if (byok) headers.set("X-Bailian-Api-Key", byok);
  const byokImg = getByokDashscopeKey();
  if (byokImg) headers.set("X-Dashscope-Api-Key", byokImg);
  return _nativeFetch(input, { ...init, headers });
}

/**
 * 为 <img> / <a download> 这类带不了 Authorization 头的直连 URL 追加 ?access_token= 兜底参数
 *（后端 auth._bearer_from_request 支持 query 兜底）。未登录时原样返回。
 */
export function withToken(url: string): string {
  const token = getAccessToken();
  if (!token || !url.includes(API_BASE)) return url;
  return `${url}${url.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(token)}`;
}

export interface IdeationSuggestion {
  product_name: string;
  reason: string;
  selling_points: string;
  category: string;
}

export interface GenerateInput {
  product_name: string;
  selling_points: string;
  /** 一句话诉求（可空 = 默认出完整上架包），由意图 Agent 判定要做什么 */
  request_text?: string;
  category: string;
  image_base64?: string;
  image_url?: string;
  platforms: string[];
}

export interface ComplianceIssue {
  check_id: string;
  severity: "error" | "warn" | string;
  field: string;
  message: string;
}

export interface AplusModule {
  type: "headline" | "grid" | "compare" | "story" | string;
  title: string;
  text: string;
  items: Record<string, string>[];
}

export interface PlatformListing {
  platform: string;
  display_name: string;
  locales: string[];
  title: string;
  bullets: string[];
  description: string;
  attributes: Record<string, string>;
  images: string[];
  detail_images?: string[];
  video_url?: string | null;
  aplus: AplusModule[];
  compliance: ComplianceIssue[];
  compliance_passed: boolean;
  import_files?: Record<string, string>;
  revised_count?: number;
}

export interface TraceEvent {
  ts: number;
  phase: string; // plan / build / heal / reflect / evolve
  tool: string;
  args_summary: string;
  result_summary: string;
  status: string; // ok / error / fallback
}

/** ⓪a 输入理解②：意图判定 —— 决定本次任务的执行图（动作空间）。 */
export interface Intent {
  /** full_package = 出完整上架包 / preview = 先出方案，暂不生成 */
  goal: string;
  /** 从诉求中解析出的目标平台（空 = 沿用请求里的选择） */
  platforms: string[];
  /** 一句话复述用户诉求，供核对 */
  summary: string;
  confidence: number;
  /** planner = 模型判定 / default = 未写诉求 / fallback = 判定失败兜底 */
  decided_by: string;
  /** 本次意图不包含的动作 —— 意图改变执行图的直接证据 */
  excluded_actions?: string[];
}

/** ⓪ 自主规划：规划 Agent 的决策产物（含规划前自主调研所调用的工具）。 */
export interface TaskPlan {
  strategy: string;
  heal_budget: number;
  focus: string;
  research_tools: string[];
  decided_by: string; // planner = 模型决策 / fallback = 回退默认
  /** 规划器声明的跳过项（仅可选动作可被跳过） */
  skip?: string[];
  /** 执行器实际生效的跳过项 —— 规划被消费的直接证据（为空 = 本次未跳过任何步骤） */
  skipped_actions?: string[];
}

/** ③ 长期记忆：被召回并注入提示词的历史教训，hit_count 为其跨任务复用次数。 */
export interface MemoryLesson {
  lesson: string;
  platform: string;
  hit_count: number;
  source_task: string;
}

/** ④ 反思迭代：本次任务蒸馏出的新教训，已写入记忆库供后续任务复用。 */
export interface AgentReflection {
  platform: string;
  lesson: string;
}

export interface TaskDetail {
  task_id: string;
  status: "queued" | "running" | "done" | "failed" | "partial" | "cancelled";
  stage: string;
  progress: number;
  request?: { product_name?: string };
  understanding?: {
    product_type?: string;
    keywords?: string[];
    selling_points?: string[];
  } | null;
  listings: PlatformListing[];
  trace?: TraceEvent[];
  // —— Agentic 能力的结构化证据 ——
  intent?: Intent | null;
  plan?: TaskPlan | null;
  memory_recall?: MemoryLesson[];
  reflections?: AgentReflection[];
  strategy_report?: string | null;
  error?: string | null;
}

export interface PackageFile {
  name: string;
  size: number;
  kind: "json" | "csv" | "image" | string;
}

export interface PackageInfo {
  task_id: string;
  product_name: string;
  platforms: string[];
  status: string;
  stage: string;
  error: string | null;
  created_at: number;
  done_at: number | null;
  platforms_done: {
    platform: string;
    display_name: string;
    passed: boolean;
    revised_count: number;
    images: number;
  }[];
  revised_total: number;
  compliance_passed_total: number;
  files: PackageFile[];
  total_size: number;
}

export interface AdminStats {
  tasks: { total: number; queued: number; running: number; done: number; failed: number };
  platforms: Record<string, number>;
  compliance: { passed: number; total: number; pass_rate: number };
  self_heal: { revised_total: number };
  images: number;
  packages_on_disk: number;
}

async function json(res: Response) {
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function createTask(input: GenerateInput) {
  const res = await qfetch(`${API_BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return json(res) as Promise<{ task_id: string }>;
}

export interface BatchItem extends GenerateInput {}

export interface BatchResult {
  batch_id: string;
  task_ids: string[];
  tasks?: TaskDetail[];
}

export interface BatchStatusItem {
  task_id: string;
  status: string;
  stage: string;
  progress: number;
  product_name: string;
  platforms: string[];
}

export interface BatchStatus {
  batch_id: string;
  total: number;
  done: number;
  running: number;
  failed: number;
  items: BatchStatusItem[];
}

export async function createBatch(items: BatchItem[], platforms?: string[]): Promise<BatchResult> {
  const res = await qfetch(`${API_BASE}/api/generate/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, platforms: platforms ?? null }),
  });
  return json(res) as Promise<BatchResult>;
}

export async function fetchBatch(batchId: string): Promise<BatchStatus> {
  return json(await qfetch(`${API_BASE}/api/batch/${batchId}`)) as Promise<BatchStatus>;
}

export async function fetchTask(taskId: string) {
  return json(await qfetch(`${API_BASE}/api/tasks/${taskId}`)) as Promise<TaskDetail>;
}

export interface AuditDraft {
  platform: string;
  category?: string;
  title?: string;
  bullets?: string[];
  description?: string;
  attributes?: Record<string, string>;
  images?: string[];
}

export interface AuditResult {
  platform: string;
  passed: boolean;
  issues: ComplianceIssue[];
}

export async function auditDraft(draft: AuditDraft) {
  const res = await qfetch(`${API_BASE}/api/audit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  return json(res) as Promise<AuditResult>;
}

export interface RuleEconomics {
  note?: string;
  currency?: string;
  commissionRate?: number;
  adTacosDefault?: number;
  returnRateDefault?: number;
  returnHandlingFee?: number;
  fulfillment?: {
    type?: string;
    fee?: number;
    note?: string;
    tiers?: { maxKg: number; fee: number }[];
    monthlyStoragePerCubicMeter?: number;
  };
  monthlyStoragePerCubicMeter?: number;
  vatRate?: number;
  dutyNote?: string;
}

export interface PlatformRule {
  platform: string;
  displayName: string;
  demoDepth: "deep" | "reuse" | "simple" | string;
  updated?: string;
  source?: string;
  locales: string[];
  marketplaces?: string[];
  title?: { maxLength?: number; recommendedLength?: number[]; formula?: string };
  bullets?: { count?: number; maxLengthPer?: number };
  description?: { maxLength?: number };
  mainImage?: {
    background?: string;
    minWidth?: number;
    minHeight?: number;
    noText?: boolean;
    noWatermark?: boolean;
    noBorder?: boolean;
  };
  categoryAttributes?: Record<string, string[]>;
  bannedWords?: Record<string, string[] | string>;
  complianceChecks?: { id: string; type: string; severity: string }[];
  economics?: RuleEconomics;
}

export async function fetchRules() {
  return json(await qfetch(`${API_BASE}/api/rules`)) as Promise<Record<string, PlatformRule>>;
}

export interface CompetitorBand {
  currency: string;
  price_min: number;
  price_max: number;
  samples?: string[];
}

export interface IdeationResult {
  market: string;
  suggestions: IdeationSuggestion[];
  trends?: string[];
  trend_source?: "live" | "none" | string;
  competitor_band?: CompetitorBand | null;
  competitor_band_source?: "demo" | "none" | string;
}

export async function requestIdeation(market: string, category: string) {
  const res = await qfetch(`${API_BASE}/api/ideation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ market, category }),
  });
  return json(res) as Promise<IdeationResult>;
}

export async function fetchTrends(market = "us") {
  return json(await qfetch(`${API_BASE}/api/trends?market=${market}`)) as Promise<{
    market: string;
    trends: string[];
    trend_source: "live" | "none" | string;
  }>;
}

export interface EconomicsInput {
  cost_cny: number;
  weight_kg: number;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  target_margin: number;
  first_mile: string;
  turnover_months: number;
  fixed_cost_cny: number;
  market_price_min?: number | null;
  market_price_max?: number | null;
}

export interface PlatformEconomics {
  platform: string;
  display_name: string;
  currency: string;
  purchase: number;
  first_mile: number;
  last_mile: number;
  storage: number;
  return_loss: number;
  commission: number;
  ad: number;
  vat: number;
  profit: number;
  margin: number;
  break_even_price: number;
  suggested_price: number;
  bep_units: number | null;
  verdict: string;
  verdict_reason: string;
}

export interface EconomicsResult {
  chargeable_weight_kg: number;
  volume_weight_kg: number;
  fx_usd_cny: number;
  fx_source?: "live" | "builtin" | string;
  platforms: PlatformEconomics[];
}

export async function runEconomics(input: EconomicsInput) {
  const res = await qfetch(`${API_BASE}/api/economics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return json(res) as Promise<EconomicsResult>;
}

export function exportUrl(taskId: string) {
  return withToken(`${API_BASE}/api/tasks/${taskId}/export`);
}

export async function submitFeedback(taskId: string, platform: string, rating: number, comment = "") {
  const res = await qfetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, platform, rating, comment }),
  });
  return json(res) as Promise<{ ok: boolean }>;
}

// ---------- Agent 中心（记忆 / 技能 / 进化提案） ----------

export interface MemoryExperience {
  id: string;
  platform: string;
  category: string;
  lesson: string;
  source_task?: string;
  hit_count: number;
  ts: number;
}

export interface MemoryFeedback {
  task_id: string;
  platform: string;
  rating: number;
  comment: string;
  ts: number;
}

export interface SkillToolInfo {
  name: string;
  type?: "prompt" | "http" | "static" | string;
  description: string;
}

export interface SkillInfo {
  id: string;
  name: string;
  version: string;
  kind?: "skill" | "connector" | string;
  description: string;
  platforms: string[];
  tools: SkillToolInfo[];
  installed_at?: number;
}

export interface SkillRegistryEntry {
  id: string;
  name: string;
  version: string;
  kind?: "skill" | "connector" | string;
  description: string;
  source: string;
  installed: boolean;
}

export interface EvolutionProposal {
  id: string;
  ts: number;
  status: "pending" | "applied" | "rejected" | "rolled_back";
  type: "prompt_patch" | "rule_patch";
  target: string;
  change: Record<string, unknown>;
  reason: string;
  evidence: string[];
  decided_at: number | null;
}

export interface HealTrendPoint {
  task_id: string;
  product_name: string;
  heal_rate: number;
  revised: number;
}

export interface AgentOverview {
  memory: {
    experiences: MemoryExperience[];
    feedback: MemoryFeedback[];
    enabled: boolean;
  };
  skills: SkillInfo[];
  proposals: { pending: number };
  metrics: { tasks: number; heal_trend: HealTrendPoint[] };
}

export async function fetchAgentOverview() {
  return json(await qfetch(`${API_BASE}/api/agent`)) as Promise<AgentOverview>;
}

export async function fetchSkillRegistry() {
  return json(await qfetch(`${API_BASE}/api/skills/registry`)) as Promise<{ registry: SkillRegistryEntry[] }>;
}

export async function installSkill(source: string) {
  const res = await qfetch(`${API_BASE}/api/skills/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  });
  return json(res) as Promise<{ ok: boolean; skill: { id: string; name: string } }>;
}

export async function uninstallSkill(skillId: string) {
  const res = await qfetch(`${API_BASE}/api/skills/${skillId}`, { method: "DELETE" });
  return json(res) as Promise<{ ok: boolean; skill_id: string }>;
}

export async function fetchProposals() {
  return json(await qfetch(`${API_BASE}/api/agent/proposals`)) as Promise<{ proposals: EvolutionProposal[] }>;
}

export async function evolveNow() {
  const res = await qfetch(`${API_BASE}/api/agent/evolve`, { method: "POST" });
  return json(res) as Promise<{ result: { generated: number; proposal?: EvolutionProposal; reason?: string } }>;
}

export async function decideProposal(id: string, action: "approve" | "reject" | "rollback") {
  const res = await qfetch(`${API_BASE}/api/agent/proposals/${id}/${action}`, { method: "POST" });
  return json(res) as Promise<{ ok: boolean; detail: string }>;
}

// ---------- 评测集（Evals：合规规则与历史事故的回归测试） ----------

export interface CaseItem {
  id: string;
  name: string;
  passed: boolean;
  skipped: boolean;
  expect: string;
  got: string;
  note: string;
}

export interface SuiteItem {
  name: string;
  desc: string;
  cases: CaseItem[];
}

export interface EvalsReport {
  generated_at: number | null;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  duration_ms: number;
  suites: SuiteItem[];
}

export async function fetchEvals() {
  return json(await qfetch(`${API_BASE}/api/evals`)) as Promise<EvalsReport>;
}

export async function runEvals() {
  const res = await qfetch(`${API_BASE}/api/evals/run`, { method: "POST" });
  return json(res) as Promise<EvalsReport>;
}

export interface ValidateDraftPayload {
  platform: string;
  category?: string;
  title?: string;
  bullets?: string[];
  description?: string;
  attributes?: Record<string, string>;
  images?: string[];
}

export interface ValidateDraftIssue {
  check_id: string;
  field: string;
  severity: string;
  message: string;
}

export interface ValidateDraftResult {
  passed: boolean;
  issues: ValidateDraftIssue[];
}

/** 草稿合规体检：POST /api/audit，归一化为 { passed, issues }（passed = 无 error 级问题）。 */
export async function validateDraft(payload: ValidateDraftPayload): Promise<ValidateDraftResult> {
  const res = await qfetch(`${API_BASE}/api/audit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await json(res) as AuditResult;
  const issues = (data.issues || []).map((i) => ({
    check_id: i.check_id ?? "",
    field: i.field,
    severity: i.severity,
    message: i.message,
  }));
  return { passed: issues.every((i) => i.severity !== "error"), issues };
}

export function zipUrl(taskId: string) {
  return withToken(`${API_BASE}/api/files/${taskId}/zip`);
}

export async function fetchFiles() {
  return json(await qfetch(`${API_BASE}/api/files`)) as Promise<{ packages: PackageInfo[] }>;
}

export async function fetchPackage(taskId: string) {
  return json(await qfetch(`${API_BASE}/api/files/${taskId}`)) as Promise<PackageInfo>;
}

export async function deletePackage(taskId: string) {
  const res = await qfetch(`${API_BASE}/api/files/${taskId}`, { method: "DELETE" });
  return json(res) as Promise<{ ok: boolean; task_id: string }>;
}

export async function fetchAdminStats() {
  return json(await qfetch(`${API_BASE}/api/admin/stats`)) as Promise<AdminStats>;
}

export async function fetchAdminTasks() {
  return json(await qfetch(`${API_BASE}/api/admin/tasks`)) as Promise<{
    tasks: {
      task_id: string;
      product_name: string;
      status: string;
      stage: string;
      platforms: string[];
      created_at: number;
      revised_total: number;
      passed_total: number;
      listing_total: number;
      error: string | null;
    }[];
  }>;
}

export function fileDownloadUrl(taskId: string, name: string) {
  return withToken(`${API_BASE}/api/files/${taskId}/download/${name}`);
}

// ---------- 上架执行（PRD v0.3：审批闸口 + 全程留痕） ----------

export interface PublishStep {
  ts: number;
  action: string; // open_page / fill_fields / upload_image / submit / live_confirm
  detail: string;
  screenshot: string | null;
}

export type PublishStatus = "queued" | "running" | "live" | "failed";

export interface PublishJob {
  job_id: string;
  task_id: string;
  platform: string;
  executor: string;
  status: PublishStatus;
  attempts: number;
  last_error: string | null;
  live_url: string | null;
  listing_id: string | null;
  sku: string;
  published_at: number | null;
  created_at: number;
  steps: PublishStep[];
}

export async function publishTask(taskId: string, platform: string) {
  const res = await qfetch(`${API_BASE}/api/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, platform, approved: true }),
  });
  return json(res) as Promise<{ job: PublishJob }>;
}

export async function fetchPublishJobs(taskId?: string) {
  const q = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
  return json(await qfetch(`${API_BASE}/api/publish/jobs${q}`)) as Promise<{ jobs: PublishJob[] }>;
}

export function publishShotUrl(jobId: string, filename: string) {
  return withToken(`${API_BASE}/api/publish/jobs/${jobId}/shots/${filename}`);
}

// ---------- 经营数据回流（PRD v0.3：数据飞轮） ----------

export interface MetricsRow {
  ts: number;
  sku: string;
  listing_id: string;
  platform: string;
  logical_hours: number;
  title_quality: number;
  impressions: number;
  clicks: number;
  ctr: number;
  conversions: number;
  anomaly: boolean;
  task_id?: string | null;
  job_id?: string | null;
}

export interface MetricsOverview {
  listings: MetricsRow[];
  anomaly_count: number;
  baseline: { ctr: number; min_impressions: number };
}

export async function fetchMetricsOverview() {
  return json(await qfetch(`${API_BASE}/api/metrics`)) as Promise<MetricsOverview>;
}

export function mockLiveUrl(listingId: string) {
  return `${API_BASE}/mock/seller-central#live/${listingId}`;
}

export const PLATFORM_META: { key: string; name: string; dot: string }[] = [
  { key: "amazon", name: "Amazon", dot: "#FF9900" },
  { key: "shopee", name: "Shopee", dot: "#EE4D2D" },
  { key: "aliexpress", name: "AliExpress", dot: "#FF4747" },
  { key: "lazada", name: "Lazada", dot: "#7C3AED" },
  { key: "tiktokshop", name: "TikTok Shop", dot: "#111827" },
];

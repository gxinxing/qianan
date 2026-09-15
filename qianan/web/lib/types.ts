/**
 * 千岸 QianAn — 前端共享类型定义
 *
 * 所有与后端 API 交互的类型统一在此导出，页面组件从 "@/lib/types" 引用，
 * 而 "@lib/api" 只负责函数封装。
 */

/* ============================
   请求类型
   ============================ */

export interface GenerateRequest {
  product_name: string;
  selling_points: string;
  category: string;
  image_base64?: string;
  image_url?: string;
  platforms: string[];
}

export interface AuditRequest {
  platform: string;
  category: string;
  title: string;
  bullets: string[];
  description: string;
  attributes: Record<string, string>;
  images: string[];
}

export interface IdeationRequest {
  market: string;
  category: string;
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

export interface FeedbackInput {
  task_id: string;
  platform: string;
  rating: 1 | -1;
  comment?: string;
}

export interface PublishRequest {
  task_id: string;
  platform: string;
  approved: boolean;
}

/* ============================
   核心响应类型
   ============================ */

export interface GenerateResponse {
  task_id: string;
}

export interface TaskStatusValue {
  queued: "queued";
  running: "running";
  done: "done";
  failed: "failed";
}

export type TaskStatus = TaskStatusValue[keyof TaskStatusValue];

export interface Understanding {
  category: string;
  product_type: string;
  material: string;
  attributes: Record<string, string>;
  selling_points: string[];
  target_audience: string;
  keywords: string[];
}

export interface ComplianceIssue {
  check_id: string;
  severity: "error" | "warn" | string;
  field: string;
  message: string;
}

export interface TaskPlan {
  strategy: string;
  heal_budget: number;
  focus: string;
  research_tools: string[];
  decided_by: string;
  /** 规划器声明的跳过项（仅可选动作可被跳过） */
  skip?: string[];
  /** 执行器实际生效的跳过项 —— 规划被消费的直接证据（为空 = 本次未跳过任何步骤） */
  skipped_actions?: string[];
}

export interface MemoryLesson {
  lesson: string;
  platform: string;
  hit_count: number;
  source_task: string;
}

export interface AgentReflection {
  platform: string;
  lesson: string;
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

export interface TaskRecord {
  task_id: string;
  status: TaskStatus;
  stage: string;
  progress: number;
  request: {
    product_name: string;
    selling_points: string;
    category: string;
    platforms: string[];
    image_url?: string;
  };
  understanding: Understanding | null;
  listings: PlatformListing[];
  trace: TraceEvent[];
  plan?: TaskPlan | null;
  memory_recall?: MemoryLesson[];
  reflections?: AgentReflection[];
  strategy_report?: string | null;
  error: string | null;
  created_at: number;
}

/* ============================
   规则库类型
   ============================ */

export interface RuleImageSpec {
  background?: string;
  minWidth?: number;
  minHeight?: number;
  noText?: boolean;
  noWatermark?: boolean;
  noBorder?: boolean;
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
  title?: {
    maxLength?: number;
    recommendedLength?: number[];
    formula?: string;
  };
  bullets?: { count?: number; maxLengthPer?: number };
  description?: { maxLength?: number };
  mainImage?: RuleImageSpec;
  categoryAttributes?: Record<string, string[]>;
  bannedWords?: Record<string, string[] | string>;
  complianceChecks?: { id: string; type: string; severity: string }[];
  economics?: RuleEconomics;
}

/* ============================
   文件管理类型
   ============================ */

export type PackageFileKind = "json" | "csv" | "image" | string;

export interface PackageFile {
  name: string;
  size: number;
  kind: PackageFileKind;
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

/* ============================
   后台管理类型
   ============================ */

export interface AdminStats {
  tasks: {
    total: number;
    queued: number;
    running: number;
    done: number;
    failed: number;
  };
  platforms: Record<string, number>;
  compliance: {
    passed: number;
    total: number;
    pass_rate: number;
  };
  self_heal: {
    revised_total: number;
  };
  images: number;
  packages_on_disk: number;
}

export interface AdminTask {
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
  source: string;
}

/* ============================
   选品灵感类型
   ============================ */

export interface IdeationSuggestion {
  product_name: string;
  reason: string;
  selling_points: string;
  category: string;
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

/* ============================
   经济测算类型
   ============================ */

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
  verdict: "green" | "yellow" | "red";
  verdict_reason: string;
}

export interface EconomicsResult {
  chargeable_weight_kg: number;
  volume_weight_kg: number;
  fx_usd_cny: number;
  fx_source?: "live" | "builtin" | string;
  platforms: PlatformEconomics[];
}

/* ============================
   Agent 中心类型
   ============================ */

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

/* ============================
   上架执行类型
   ============================ */

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

/* ============================
   经营数据回流类型
   ============================ */

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

/* ============================
   共享 UI 类型
   ============================ */

export interface PlatformMeta {
  key: string;
  name: string;
  dot: string;
}

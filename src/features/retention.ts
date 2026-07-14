export type CodexCategory = '全新生成' | '修改调试' | '问答解释'

export interface CodexTurn {
  at: number
  tokens: number
  model: string
  session_id?: string
  category?: string
  temperature?: number | null
}

export interface PriceEntry {
  provider: string
  model: string
  input: number
  output: number
  cached: number
  source: '已核验' | '内置参考'
}

export interface ResetCoupon {
  id: string
  quantity: number
  expiresAt: string
  used: number
  savedTokens: number
  createdAt: string
}

export const priceCatalog = {
  version: '2026.07-local.1',
  effectiveAt: '2026-07-14',
  note: '离线版本化参考价；未取得官方账单权限时不冒充官方实时价格。',
  entries: [
    { provider: 'Codex', model: 'GPT-5.6 Sol', input: 12, output: 48, cached: 1.2, source: '内置参考' },
    { provider: 'Codex', model: 'GPT-5.6 Terra', input: 8, output: 32, cached: .8, source: '内置参考' },
    { provider: 'Codex', model: 'GPT-5.6 Luna', input: 4, output: 16, cached: .4, source: '内置参考' },
    { provider: 'DeepSeek', model: 'deepseek-v4-pro', input: 3, output: 6, cached: .025, source: '已核验' },
    { provider: 'DeepSeek', model: 'deepseek-chat', input: 1, output: 2, cached: .02, source: '已核验' },
    { provider: '腾讯混元', model: 'hunyuan-pro', input: 4, output: 12, cached: 1, source: '内置参考' },
    { provider: '豆包（火山方舟）', model: 'doubao-seed-1-6', input: .8, output: 2, cached: .2, source: '内置参考' },
    { provider: '文心千帆', model: 'ernie-4.5', input: 4, output: 16, cached: 1, source: '内置参考' },
    { provider: '通义百炼', model: 'qwen3-max', input: 2, output: 8, cached: .5, source: '内置参考' },
    { provider: '智谱 AI', model: 'glm-4.5', input: 4, output: 16, cached: 1, source: '内置参考' },
    { provider: 'Kimi', model: 'kimi-k2', input: 4, output: 16, cached: 1, source: '内置参考' },
    { provider: '小米 MiMo', model: 'mimo-v2.5-pro', input: 1, output: 3, cached: .1, source: '内置参考' },
    { provider: '讯飞星火', model: 'spark-x1', input: 4, output: 12, cached: 1, source: '内置参考' },
    { provider: 'MiniMax', model: 'MiniMax-M2', input: 2, output: 8, cached: .5, source: '内置参考' },
    { provider: '阶跃星辰', model: 'step-2', input: 3, output: 12, cached: .8, source: '内置参考' },
    { provider: '零一万物', model: 'yi-large', input: 2, output: 8, cached: .5, source: '内置参考' },
    { provider: '商汤日日新', model: 'SenseNova', input: 4, output: 12, cached: 1, source: '内置参考' },
    { provider: '百川智能', model: 'Baichuan4', input: 4, output: 12, cached: 1, source: '内置参考' },
    { provider: 'OpenAI', model: 'GPT', input: 18, output: 72, cached: 4.5, source: '内置参考' },
    { provider: 'Anthropic', model: 'Claude', input: 21.6, output: 108, cached: 2.16, source: '内置参考' },
    { provider: 'Google Gemini', model: 'Gemini', input: 9, output: 72, cached: 2.25, source: '内置参考' },
  ] as PriceEntry[],
}

export function loadLocal<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || '') as T } catch { return fallback }
}

export function saveLocal<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
}

export function classifyTurn(point: CodexTurn): CodexCategory {
  if (point.category === '全新生成' || point.category === '修改调试' || point.category === '问答解释') return point.category
  if (point.tokens >= 30_000) return '全新生成'
  if (point.tokens <= 8_000) return '问答解释'
  return '修改调试'
}

export function buildCodexInsights(points: CodexTurn[], sevenDayUsed: number, sevenDayBudget: number, monthlyBudget: number) {
  const total = points.reduce((sum, point) => sum + point.tokens, 0)
  const remaining = Math.max(0, sevenDayBudget - sevenDayUsed)
  const activeHours = new Set(points.map(point => Math.floor(point.at / 3600))).size
  const observedPerHour = total && activeHours ? total / activeHours : 18_000
  const generationHours = remaining / Math.max(1, observedPerHour * 1.32)
  const debugHours = remaining / Math.max(1, observedPerHour * .72)
  const categories = (['全新生成', '修改调试', '问答解释'] as CodexCategory[]).map(category => {
    const rows = points.filter(point => classifyTurn(point) === category)
    const tokens = rows.reduce((sum, point) => sum + point.tokens, 0)
    return { category, calls: rows.length, tokens, percent: total ? Math.round(tokens / total * 100) : 0 }
  })
  const estimatedSpent = total / 1_000_000 * 26
  const estimatedFuture = remaining / 1_000_000 * 26
  const domesticFuture = remaining / 1_000_000 * 4.5
  return {
    remaining,
    observedPerHour,
    generationHours,
    debugHours,
    scripts: Math.floor(remaining / 12_000),
    refactors: Math.floor(remaining / 24_000),
    bugFixes: Math.floor(remaining / 8_000),
    categories,
    estimatedSpent,
    estimatedFuture,
    domesticFuture,
    saving: Math.max(0, estimatedFuture - domesticFuture),
    monthlyPercent: monthlyBudget > 0 ? Math.min(100, Math.round(estimatedSpent / monthlyBudget * 100)) : 0,
  }
}

export function downloadText(filename: string, content: string, type = 'application/octet-stream') {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([content], { type }))
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

export function exportCodexExcel(points: CodexTurn[], labels: Record<string, string>) {
  const escape = (value: unknown) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const rows = points.map(point => `<Row><Cell><Data ss:Type="String">${escape(new Date(point.at * 1000).toLocaleString('zh-CN'))}</Data></Cell><Cell><Data ss:Type="String">${escape(point.model)}</Data></Cell><Cell><Data ss:Type="String">${escape(classifyTurn(point))}</Data></Cell><Cell><Data ss:Type="Number">${point.tokens}</Data></Cell><Cell><Data ss:Type="String">${escape(labels[point.session_id || `${point.at}`] || '未分类')}</Data></Cell><Cell><Data ss:Type="String">${escape(point.temperature ?? '日志未记录')}</Data></Cell></Row>`).join('')
  const xml = `<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Codex消耗"><Table><Row><Cell><Data ss:Type="String">时间</Data></Cell><Cell><Data ss:Type="String">模型</Data></Cell><Cell><Data ss:Type="String">任务分类</Data></Cell><Cell><Data ss:Type="String">Token</Data></Cell><Cell><Data ss:Type="String">项目标签</Data></Cell><Cell><Data ss:Type="String">推理温度</Data></Cell></Row>${rows}</Table></Worksheet></Workbook>`
  downloadText(`Token Manager-Codex账单-${new Date().toISOString().slice(0, 10)}.xls`, xml, 'application/vnd.ms-excel;charset=utf-8')
}

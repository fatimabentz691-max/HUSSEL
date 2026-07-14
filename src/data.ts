import type { Provider, Usage, Dashboard } from './types'
export const providers: Provider[] = [
 ['hunyuan','腾讯混元'],['doubao','豆包（火山方舟）'],['qianfan','文心千帆'],['bailian','通义百炼'],['zhipu','智谱 AI'],['deepseek','DeepSeek'],['kimi','Kimi'],['mimo','小米 MiMo'],['spark','讯飞星火'],['minimax','MiniMax'],['stepfun','阶跃星辰'],['yi','零一万物'],['sensenova','商汤日日新'],['baichuan','百川智能'],['openai','OpenAI'],['anthropic','Anthropic'],['gemini','Google Gemini'],['custom','自定义 OpenAI 兼容']
].map(([id,name]) => ({ id, name, source: id === 'deepseek' ? '官方账单' : '本地代理', description:'尚未配置', configured:false, models:[] }))
export const demoUsage: Usage[] = [
 {id:'1',provider:'Codex',model:'codex',at:new Date().toISOString(),input:24000,output:8600,cached:3200,cost:0,task:'调试'},
 {id:'2',provider:'DeepSeek',model:'deepseek-chat',at:new Date(Date.now()-864e5).toISOString(),input:128000,output:42000,cached:0,cost:3.82,task:'生成'},
 {id:'3',provider:'智谱 AI',model:'glm-4',at:new Date(Date.now()-2*864e5).toISOString(),input:42000,output:9000,cached:8000,cost:1.25,task:'文档'}
]
export const demoDashboard: Dashboard = { today: 2.48, week: 12.60, balance: null, input:194000, output:59600, codex5h:0, codex7d:0, resetAt:new Date().toISOString() }

export type SourceKind = '官方账单' | '本地代理' | '账单导入' | '本地日志' | '不可用'
export interface Provider { id:string; name:string; source:SourceKind; description:string; configured:boolean; models:string[] }
export interface Usage { id:string; provider:string; model:string; at:string; input:number; output:number; cached:number; cost:number; task:'生成'|'调试'|'文档'|'其他'|'失败' }
export interface Dashboard { today:number; week:number; balance:number|null; input:number; output:number; codex5h:number; codex7d:number; resetAt:string }

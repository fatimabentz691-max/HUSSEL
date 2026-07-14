use chrono::{DateTime, Utc};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, fs, net::{SocketAddr, TcpStream}, path::PathBuf, process::Command, sync::Mutex, time::Duration};
use tauri::{menu::{Menu, MenuItem}, tray::TrayIconBuilder, AppHandle, Emitter, Manager, State, WindowEvent};
use axum::{body::Body, extract::State as AxumState, http::{Request, Response, StatusCode}, routing::any, Router};
use tauri_plugin_notification::NotificationExt;
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use chacha20poly1305::{aead::{Aead, KeyInit}, ChaCha20Poly1305, Nonce};
use pbkdf2::pbkdf2_hmac;
use rand::RngCore;
use sha2::Sha256;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct UsageEvent { pub id:String, pub provider:String, pub model:String, pub at:DateTime<Utc>, pub input:u64, pub output:u64, pub cached:u64, pub cost:f64, pub task:String }
/// 从 Codex 本地状态库读取的可验证汇总，不包含服务端会员额度。
#[derive(Debug, Serialize)]
pub struct CodexSnapshot { pub total_tokens:u64, pub active_thread_tokens:u64, pub updated_at_ms:i64, pub source:String }
#[derive(Debug, Serialize)]
pub struct CodexBudget { pub five_hour_limit:u64, pub seven_day_limit:u64 }
#[derive(Debug, Serialize)]
pub struct CodexWindowUsage { pub five_hour_used:u64, pub seven_day_used:u64, pub budget:CodexBudget, pub source:String }
#[derive(Debug, Serialize)]
pub struct CodexUsagePoint { pub at:i64, pub tokens:u64, pub model:String, pub session_id:String, pub category:String, pub temperature:Option<f64> }
#[derive(Debug, Serialize)]
pub struct AccountSummary { pub id:String, pub provider:String, pub name:String, pub base_url:String, pub created_at:String }
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AccountBalance { pub account_id:String, pub provider:String, pub currency:String, pub total_balance:f64, pub granted_balance:f64, pub topped_up_balance:f64, pub is_available:bool, pub synced_at:String }
#[derive(Debug, Serialize)]
pub struct BalancePoint { pub at:String, pub total_balance:f64 }
#[derive(Debug, Serialize, Clone)]
pub struct ProxyEndpoint { pub account_id:String, pub provider:String, pub name:String, pub local_url:String, pub port:u16 }
#[derive(Debug, Serialize)]
pub struct CcSwitchStatus { pub installed:bool, pub running:bool, pub local_routing:bool, pub detail:String, pub checked_at:String }
#[derive(Debug, Serialize, Deserialize)]
struct BackupAccount { id:String, provider:String, name:String, base_url:String, api_key:String, created_at:String }
#[derive(Debug, Serialize, Deserialize)]
struct BackupBundle { version:u8, exported_at:String, accounts:Vec<BackupAccount>, usage:Vec<UsageEvent>, balances:Vec<AccountBalance>, five_hour_limit:u64, seven_day_limit:u64, ui_state:serde_json::Value }
#[derive(Debug, Serialize, Deserialize)]
struct BackupEnvelope { version:u8, salt:String, nonce:String, ciphertext:String }
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AdapterCapability { pub provider:String, pub billing:bool, pub proxy:bool, pub import:bool, pub note:String }
pub trait ProviderAdapter: Send + Sync { fn capability(&self)->AdapterCapability; fn normalize(&self, value:&serde_json::Value)->Option<UsageEvent>; }
pub struct RegistryAdapter { id:&'static str, billing:bool }
impl ProviderAdapter for RegistryAdapter {
 fn capability(&self)->AdapterCapability { AdapterCapability { provider:self.id.into(), billing:self.billing, proxy:true, import:true, note: if self.billing { "需使用对应官方账单接口及账户权限".into() } else { "使用本地代理或账单导入统计".into() } } }
 fn normalize(&self, value:&serde_json::Value)->Option<UsageEvent> { Some(UsageEvent { id:uuid_like(), provider:self.id.into(), model:value.get("model")?.as_str()?.into(), at:Utc::now(), input:value.pointer("/usage/prompt_tokens").and_then(|v|v.as_u64()).unwrap_or(0), output:value.pointer("/usage/completion_tokens").and_then(|v|v.as_u64()).unwrap_or(0), cached:0, cost:0.0, task:"其他".into() }) }
}
fn uuid_like()->String { format!("evt-{}", Utc::now().timestamp_micros()) }
pub struct AppDb(Mutex<Connection>);
pub struct ProxyServerState(Mutex<HashMap<u16,String>>);
impl AppDb { fn open()->Self { let path=data_path(); let db=Connection::open(path).expect("无法打开本地数据库"); db.execute_batch("CREATE TABLE IF NOT EXISTS usage_events(id TEXT PRIMARY KEY,provider TEXT,model TEXT,at TEXT,input_tokens INTEGER,output_tokens INTEGER,cached_tokens INTEGER,cost REAL,task TEXT); CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,provider TEXT,name TEXT,secret_cipher BLOB,created_at TEXT); CREATE TABLE IF NOT EXISTS account_configs(id TEXT PRIMARY KEY,provider TEXT NOT NULL,name TEXT NOT NULL,base_url TEXT NOT NULL,secret_cipher BLOB NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS codex_budget(id INTEGER PRIMARY KEY CHECK(id=1),five_hour_limit INTEGER NOT NULL,seven_day_limit INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS account_balances(account_id TEXT NOT NULL,provider TEXT NOT NULL,currency TEXT NOT NULL,total_balance REAL NOT NULL,granted_balance REAL NOT NULL,topped_up_balance REAL NOT NULL,is_available INTEGER NOT NULL,synced_at TEXT NOT NULL,PRIMARY KEY(account_id,currency)); CREATE TABLE IF NOT EXISTS balance_history(id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL,currency TEXT NOT NULL,total_balance REAL NOT NULL,at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS idx_balance_history_account_at ON balance_history(account_id,at);").expect("无法初始化数据库"); db.execute("INSERT OR IGNORE INTO codex_budget(id,five_hour_limit,seven_day_limit) VALUES(1,100000,1000000)",[]).expect("无法创建默认预算"); Self(Mutex::new(db)) } }
fn data_path()->PathBuf {let base=dirs::data_local_dir().unwrap_or_else(||PathBuf::from("."));let root=base.join("Token Manager");fs::create_dir_all(&root).ok();let next=root.join("token-manager.db");let legacy=base.join("TokenLens").join("tokenlens.db");if !next.exists()&&legacy.exists(){fs::copy(legacy,&next).ok();}next}
#[derive(Clone)]
struct ProxyRuntime { upstream:String, provider:String, account_id:Option<String>, api_key:Option<String>, client:reqwest::Client, app:AppHandle }
fn deepseek_cost(model:&str,input:u64,output:u64,cached:u64)->f64 { let pro=model.eq_ignore_ascii_case("deepseek-v4-pro");let (hit,miss,out)=if pro{(0.025,3.0,6.0)}else{(0.02,1.0,2.0)};let uncached=input.saturating_sub(cached);(cached as f64*hit+uncached as f64*miss+output as f64*out)/1_000_000.0 }
/// 离线版本化人民币参考价（元/百万 Token）；DeepSeek 使用已核验规则，其余平台明确标记为内置参考价。
fn provider_cost(provider:&str,model:&str,input:u64,output:u64,cached:u64)->f64{if provider=="DeepSeek"{return deepseek_cost(model,input,output,cached)}let (hit,miss,out)=match provider{"腾讯混元"=>(1.0,4.0,12.0),"豆包（火山方舟）"=>(0.2,0.8,2.0),"文心千帆"=>(1.0,4.0,16.0),"通义百炼"=>(0.5,2.0,8.0),"智谱 AI"=>(1.0,4.0,16.0),"Kimi"=>(1.0,4.0,16.0),"小米 MiMo"=>(0.1,1.0,3.0),"讯飞星火"=>(1.0,4.0,12.0),"MiniMax"=>(0.5,2.0,8.0),"阶跃星辰"=>(0.8,3.0,12.0),"零一万物"=>(0.5,2.0,8.0),"商汤日日新"=>(1.0,4.0,12.0),"百川智能"=>(1.0,4.0,12.0),"OpenAI"=>(4.5,18.0,72.0),"Anthropic"=>(2.16,21.6,108.0),"Google Gemini"=>(2.25,9.0,72.0),_=>return 0.0};let uncached=input.saturating_sub(cached);(cached as f64*hit+uncached as f64*miss+output as f64*out)/1_000_000.0}
fn usage_values(body:&[u8])->Vec<serde_json::Value>{if let Ok(value)=serde_json::from_slice::<serde_json::Value>(body){return match value{serde_json::Value::Array(rows)=>rows,_=>vec![value]}}let text=String::from_utf8_lossy(body);text.lines().filter_map(|line|{let data=line.trim().strip_prefix("data:")?.trim();if data=="[DONE]"{None}else{serde_json::from_str::<serde_json::Value>(data).ok()}}).collect()}
fn usage_counts(value:&serde_json::Value)->Option<(u64,u64,u64)>{if let Some(usage)=value.get("usage"){let input=usage.get("prompt_tokens").or_else(||usage.get("input_tokens")).and_then(|v|v.as_u64()).unwrap_or(0);let output=usage.get("completion_tokens").or_else(||usage.get("output_tokens")).and_then(|v|v.as_u64()).unwrap_or(0);let cached=usage.get("prompt_cache_hit_tokens").or_else(||usage.get("cache_read_input_tokens")).or_else(||usage.pointer("/prompt_tokens_details/cached_tokens")).or_else(||usage.pointer("/input_tokens_details/cached_tokens")).and_then(|v|v.as_u64()).unwrap_or(0);return Some((input,output,cached))}if let Some(usage)=value.get("usageMetadata"){let input=usage.get("promptTokenCount").and_then(|v|v.as_u64()).unwrap_or(0);let output=usage.get("candidatesTokenCount").and_then(|v|v.as_u64()).unwrap_or(0)+usage.get("thoughtsTokenCount").and_then(|v|v.as_u64()).unwrap_or(0);let cached=usage.get("cachedContentTokenCount").and_then(|v|v.as_u64()).unwrap_or(0);return Some((input,output,cached))}None}
fn response_usage(body:&[u8], model:&str, provider:&str,status:u16) {
 let mut input=0;let mut output=0;let mut cached=0;for value in usage_values(body){if let Some((next_input,next_output,next_cached))=usage_counts(&value){input=input.max(next_input);output=output.max(next_output);cached=cached.max(next_cached)}}let cost=provider_cost(provider,model,input,output,cached);let task=if status>=400{"失败"}else{"其他"};let Ok(db)=Connection::open(data_path()) else{return};let _=db.execute("INSERT INTO usage_events VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)",params![uuid_like(),provider,model,Utc::now().to_rfc3339(),input,output,cached,cost,task]);
}

async fn fetch_and_store_deepseek_balance(account_id:&str,base_url:&str,key:&str)->Result<Vec<AccountBalance>,String>{let base=base_url.trim_end_matches('/').trim_end_matches("/v1");let value=reqwest::Client::new().get(format!("{base}/user/balance")).bearer_auth(key).header("Accept","application/json").send().await.map_err(|e|format!("DeepSeek 余额请求失败：{e}"))?.error_for_status().map_err(|e|format!("DeepSeek 余额接口返回错误：{e}"))?.json::<serde_json::Value>().await.map_err(|e|format!("DeepSeek 余额数据无法解析：{e}"))?;let available=value.get("is_available").and_then(|v|v.as_bool()).unwrap_or(false);let now=Utc::now().to_rfc3339();let mut rows=Vec::new();for item in value.get("balance_infos").and_then(|v|v.as_array()).into_iter().flatten(){let currency=item.get("currency").and_then(|v|v.as_str()).unwrap_or("CNY").to_string();let parse=|name:&str|item.get(name).and_then(|v|v.as_str()).and_then(|v|v.parse::<f64>().ok()).unwrap_or(0.0);rows.push(AccountBalance{account_id:account_id.into(),provider:"DeepSeek".into(),currency,total_balance:parse("total_balance"),granted_balance:parse("granted_balance"),topped_up_balance:parse("topped_up_balance"),is_available:available,synced_at:now.clone()});}let db=Connection::open(data_path()).map_err(|e|e.to_string())?;for row in &rows{db.execute("INSERT OR REPLACE INTO account_balances(account_id,provider,currency,total_balance,granted_balance,topped_up_balance,is_available,synced_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8)",params![row.account_id,row.provider,row.currency,row.total_balance,row.granted_balance,row.topped_up_balance,row.is_available as i32,row.synced_at]).map_err(|e|e.to_string())?;db.execute("INSERT INTO balance_history(account_id,currency,total_balance,at) SELECT ?1,?2,?3,?4 WHERE NOT EXISTS(SELECT 1 FROM balance_history WHERE account_id=?1 AND currency=?2 AND total_balance=?3 AND at>=datetime(?4,'-30 seconds'))",params![row.account_id,row.currency,row.total_balance,row.synced_at]).map_err(|e|e.to_string())?;}Ok(rows)}
async fn proxy_request(AxumState(runtime):AxumState<ProxyRuntime>, request:Request<Body>)->Result<Response<Body>,(StatusCode,String)> {
 let (parts,body)=request.into_parts(); let payload=axum::body::to_bytes(body,20*1024*1024).await.map_err(|e|(StatusCode::BAD_REQUEST,e.to_string()))?;let path=parts.uri.path_and_query().map(|v|v.as_str()).unwrap_or("/");let model=serde_json::from_slice::<serde_json::Value>(&payload).ok().and_then(|v|v.get("model").and_then(|m|m.as_str()).map(str::to_owned)).or_else(||path.split("/models/").nth(1).and_then(|v|v.split([':', '?']).next()).map(str::to_owned)).unwrap_or_else(||"unknown".into());
 let base=runtime.upstream.trim_end_matches('/');let path=if ["/v1","/v2","/v3","/v4"].iter().any(|suffix|base.ends_with(suffix)){path.strip_prefix("/v1").unwrap_or(path)}else{path};let url=format!("{base}{path}");
 let method=reqwest::Method::from_bytes(parts.method.as_str().as_bytes()).map_err(|e|(StatusCode::BAD_REQUEST,e.to_string()))?;
 let has_auth=parts.headers.contains_key("authorization"); let mut outbound=runtime.client.request(method,url).body(payload); for (name,value) in parts.headers.iter(){if name.as_str().eq_ignore_ascii_case("host"){continue}outbound=outbound.header(name,value);}if !has_auth{if let Some(key)=&runtime.api_key{outbound=outbound.bearer_auth(key)}}
 let remote=match outbound.send().await{Ok(response)=>response,Err(error)=>{response_usage(&[],&model,&runtime.provider,StatusCode::BAD_GATEWAY.as_u16());runtime.app.emit("usage-updated",runtime.provider.clone()).ok();return Err((StatusCode::BAD_GATEWAY,format!("上游请求失败：{error}")))}}; let status=remote.status(); let headers=remote.headers().clone(); let bytes=remote.bytes().await.map_err(|e|(StatusCode::BAD_GATEWAY,e.to_string()))?;
 response_usage(&bytes,&model,&runtime.provider,status.as_u16());if runtime.provider=="DeepSeek"{if let (Some(id),Some(key))=(&runtime.account_id,&runtime.api_key){let _=fetch_and_store_deepseek_balance(id,&runtime.upstream,key).await;}}runtime.app.emit("usage-updated",runtime.provider.clone()).ok();let mut builder=Response::builder().status(status); for (name,value) in headers.iter(){builder=builder.header(name,value);} builder.body(Body::from(bytes)).map_err(|e|(StatusCode::INTERNAL_SERVER_ERROR,e.to_string()))
}
#[tauri::command]
fn start_proxy(upstream:String,port:u16,account_id:Option<String>,state:State<ProxyServerState>,db_state:State<AppDb>,app:AppHandle)->Result<String,String>{
 if !upstream.starts_with("https://") && !upstream.starts_with("http://127.0.0.1") && !upstream.starts_with("http://localhost"){return Err("上游地址必须使用 HTTPS，或为本机地址".into())}
 let mut running=state.0.lock().map_err(|_|"代理状态锁定")?;if running.contains_key(&port){return Err(format!("端口 {port} 的本地代理已在运行"))}running.insert(port,account_id.clone().unwrap_or_else(||"custom".into()));drop(running);
 let selected_account=account_id.clone();let (api_key,provider)=if let Some(id)=account_id{let db=db_state.0.lock().map_err(|_|"数据库锁定")?;let (cipher,provider):(Vec<u8>,String)=db.query_row("SELECT secret_cipher,provider FROM account_configs WHERE id=?1",[id],|r|Ok((r.get(0)?,r.get(1)?))).map_err(|_|"未找到已配置账户")?;(Some(unprotect_secret(&cipher)?),provider)}else{(None,"自定义 OpenAI 兼容".into())};let runtime=ProxyRuntime{upstream,provider,account_id:selected_account,api_key,client:reqwest::Client::new(),app};tauri::async_runtime::spawn(async move{let router=Router::new().fallback(any(proxy_request)).with_state(runtime);if let Ok(listener)=tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST,port)).await{let _=axum::serve(listener,router).await;}});Ok(format!("http://127.0.0.1:{port}/v1"))
}
#[tauri::command]
fn start_all_proxies(state:State<ProxyServerState>,db_state:State<AppDb>,app:AppHandle)->Result<Vec<ProxyEndpoint>,String>{let accounts={let db=db_state.0.lock().map_err(|_|"数据库锁定")?;let mut query=db.prepare("SELECT id,provider,name,base_url,secret_cipher FROM account_configs ORDER BY created_at ASC").map_err(|e|e.to_string())?;let rows=query.query_map([],|r|Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,String>(3)?,r.get::<_,Vec<u8>>(4)?))).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())?;rows};if accounts.is_empty(){return Err("请先在“账户与模型”中添加至少一个 API 账户".into())}let mut endpoints=Vec::new();let mut running=state.0.lock().map_err(|_|"代理状态锁定")?;for (index,(id,provider,name,upstream,cipher)) in accounts.into_iter().enumerate(){let port=18765u16.saturating_add(index as u16);let local_url=format!("http://127.0.0.1:{port}/v1");if !running.contains_key(&port){let key=unprotect_secret(&cipher)?;let runtime=ProxyRuntime{upstream,provider:provider.clone(),account_id:Some(id.clone()),api_key:Some(key),client:reqwest::Client::new(),app:app.clone()};tauri::async_runtime::spawn(async move{let router=Router::new().fallback(any(proxy_request)).with_state(runtime);if let Ok(listener)=tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST,port)).await{let _=axum::serve(listener,router).await;}});running.insert(port,id.clone());}endpoints.push(ProxyEndpoint{account_id:id,provider,name,local_url,port});}app.emit("proxy-state",endpoints.clone()).ok();Ok(endpoints)}
#[cfg(windows)] fn protect_secret(value:&str)->Result<Vec<u8>,String>{use windows_sys::Win32::{Foundation::LocalFree,Security::Cryptography::{CryptProtectData,CRYPT_INTEGER_BLOB}};let mut input=value.as_bytes().to_vec();let source=CRYPT_INTEGER_BLOB{cbData:input.len() as u32,pbData:input.as_mut_ptr()};let mut output=CRYPT_INTEGER_BLOB::default();let ok=unsafe{CryptProtectData(&source,std::ptr::null(),std::ptr::null(),std::ptr::null(),std::ptr::null(),0,&mut output)};if ok==0{return Err("DPAPI 加密失败".into())}let data=unsafe{std::slice::from_raw_parts(output.pbData,output.cbData as usize).to_vec()};unsafe{LocalFree(output.pbData.cast())};Ok(data)}
#[cfg(windows)] fn unprotect_secret(value:&[u8])->Result<String,String>{use windows_sys::Win32::{Foundation::LocalFree,Security::Cryptography::{CryptUnprotectData,CRYPT_INTEGER_BLOB}};let mut input=value.to_vec();let source=CRYPT_INTEGER_BLOB{cbData:input.len() as u32,pbData:input.as_mut_ptr()};let mut output=CRYPT_INTEGER_BLOB::default();let ok=unsafe{CryptUnprotectData(&source,std::ptr::null_mut(),std::ptr::null(),std::ptr::null(),std::ptr::null(),0,&mut output)};if ok==0{return Err("DPAPI 解密失败".into())}let data=unsafe{std::slice::from_raw_parts(output.pbData,output.cbData as usize).to_vec()};unsafe{LocalFree(output.pbData.cast())};String::from_utf8(data).map_err(|_|"密钥格式无效".into())}
#[cfg(not(windows))] fn protect_secret(_: &str)->Result<Vec<u8>,String>{Err("仅支持 Windows DPAPI".into())}#[cfg(not(windows))] fn unprotect_secret(_: &[u8])->Result<String,String>{Err("仅支持 Windows DPAPI".into())}
#[tauri::command] fn save_account_config(id:String,provider:String,name:String,base_url:String,api_key:String,state:State<AppDb>)->Result<(),String>{let db=state.0.lock().map_err(|_|"数据库锁定")?;let cipher=if api_key.trim().is_empty(){db.query_row("SELECT secret_cipher FROM account_configs WHERE id=?1",[&id],|r|r.get::<_,Vec<u8>>(0)).map_err(|_|"新账户必须输入 API Key")?}else{protect_secret(&api_key)?};db.execute("INSERT OR REPLACE INTO account_configs(id,provider,name,base_url,secret_cipher,created_at) VALUES(?1,?2,?3,?4,?5,COALESCE((SELECT created_at FROM account_configs WHERE id=?1),?6))",params![id,provider,name,base_url,cipher,Utc::now().to_rfc3339()]).map_err(|e|e.to_string())?;Ok(())}
#[tauri::command] fn list_account_configs(state:State<AppDb>)->Result<Vec<AccountSummary>,String>{let db=state.0.lock().map_err(|_|"数据库锁定")?;let mut query=db.prepare("SELECT id,provider,name,base_url,created_at FROM account_configs ORDER BY created_at DESC").map_err(|e|e.to_string())?;let result=query.query_map([],|r|Ok(AccountSummary{id:r.get(0)?,provider:r.get(1)?,name:r.get(2)?,base_url:r.get(3)?,created_at:r.get(4)?})).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string());result}
#[tauri::command] fn delete_account_config(id:String,state:State<AppDb>)->Result<(),String>{let db=state.0.lock().map_err(|_|"数据库锁定")?;db.execute("DELETE FROM account_configs WHERE id=?1",[&id]).map_err(|e|e.to_string())?;db.execute("DELETE FROM account_balances WHERE account_id=?1",[&id]).map_err(|e|e.to_string())?;db.execute("DELETE FROM balance_history WHERE account_id=?1",[&id]).map_err(|e|e.to_string())?;Ok(())}
#[tauri::command] fn clear_account_configs(state:State<AppDb>)->Result<(),String>{let db=state.0.lock().map_err(|_|"数据库锁定")?;db.execute_batch("DELETE FROM account_configs;DELETE FROM account_balances;DELETE FROM balance_history;").map_err(|e|e.to_string())?;Ok(())}
#[tauri::command]
async fn sync_account_balances(state:State<'_,AppDb>)->Result<Vec<AccountBalance>,String>{let accounts={let db=state.0.lock().map_err(|_|"数据库锁定")?;let mut query=db.prepare("SELECT id,base_url,secret_cipher FROM account_configs WHERE provider='DeepSeek'").map_err(|e|e.to_string())?;let rows=query.query_map([],|r|Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,Vec<u8>>(2)?))).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())?;rows};let mut balances=Vec::new();let mut errors=Vec::new();for (id,base,cipher) in accounts{match unprotect_secret(&cipher){Ok(key)=>match fetch_and_store_deepseek_balance(&id,&base,&key).await{Ok(mut rows)=>balances.append(&mut rows),Err(error)=>errors.push(error)},Err(error)=>errors.push(error)}}if balances.is_empty()&&!errors.is_empty(){Err(errors.join("；"))}else{Ok(balances)}}
#[tauri::command]
fn list_account_balances(state:State<AppDb>)->Result<Vec<AccountBalance>,String>{let db=state.0.lock().map_err(|_|"数据库锁定")?;let mut query=db.prepare("SELECT account_id,provider,currency,total_balance,granted_balance,topped_up_balance,is_available,synced_at FROM account_balances ORDER BY synced_at DESC").map_err(|e|e.to_string())?;let rows=query.query_map([],|r|Ok(AccountBalance{account_id:r.get(0)?,provider:r.get(1)?,currency:r.get(2)?,total_balance:r.get(3)?,granted_balance:r.get(4)?,topped_up_balance:r.get(5)?,is_available:r.get::<_,i64>(6)?!=0,synced_at:r.get(7)?})).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())?;Ok(rows)}
#[tauri::command]
fn list_balance_history(account_id:String,days:i64,state:State<AppDb>)->Result<Vec<BalancePoint>,String>{let since=(Utc::now()-chrono::Duration::days(days.clamp(1,365))).to_rfc3339();let db=state.0.lock().map_err(|_|"数据库锁定")?;let mut query=db.prepare("SELECT at,total_balance FROM balance_history WHERE account_id=?1 AND currency='CNY' AND at>=?2 ORDER BY at ASC").map_err(|e|e.to_string())?;let rows=query.query_map(params![account_id,since],|r|Ok(BalancePoint{at:r.get(0)?,total_balance:r.get(1)?})).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())?;Ok(rows)}
#[tauri::command] async fn fetch_account_models(id:String,state:State<'_,AppDb>)->Result<Vec<String>,String>{let (provider,base_url,cipher):(String,String,Vec<u8>)={let db=state.0.lock().map_err(|_|"数据库锁定")?;db.query_row("SELECT provider,base_url,secret_cipher FROM account_configs WHERE id=?1",[id],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?))).map_err(|_|"未找到已配置账户")?};let key=unprotect_secret(&cipher)?;let base=base_url.trim_end_matches('/');let url=if provider=="Google Gemini"{format!("{base}/v1beta/models?key={key}")}else if base.ends_with("/v1")||base.ends_with("/v2")||base.ends_with("/v4"){format!("{base}/models")}else{format!("{base}/v1/models")};let client=reqwest::Client::new();let mut request=client.get(url);if provider=="Anthropic"{request=request.header("x-api-key",key).header("anthropic-version","2023-06-01");}else if provider!="Google Gemini"{request=request.bearer_auth(key);}let value=request.send().await.map_err(|e|format!("模型列表请求失败：{e}"))?.error_for_status().map_err(|e|format!("模型列表接口返回错误：{e}"))?.json::<serde_json::Value>().await.map_err(|e|format!("无法解析模型列表：{e}"))?;let mut models=if provider=="Google Gemini"{value.get("models").and_then(|v|v.as_array()).into_iter().flatten().filter_map(|v|v.get("name").and_then(|x|x.as_str()).map(|s|s.trim_start_matches("models/").to_string())).collect::<Vec<_>>()}else{value.get("data").and_then(|v|v.as_array()).into_iter().flatten().filter_map(|v|v.get("id").and_then(|x|x.as_str()).map(str::to_string)).collect::<Vec<_>>()};models.sort();models.dedup();Ok(models)}
fn show_floating(app:&AppHandle)->Result<(),String>{let window=app.get_webview_window("floating").ok_or("悬浮窗口尚未初始化")?;window.show().map_err(|e|e.to_string())?;window.set_always_on_top(true).map_err(|e|e.to_string())?;window.set_focus().ok();app.emit("floating-state",true).ok();Ok(())}
#[tauri::command] fn set_floating_window(enabled:bool,app:AppHandle)->Result<(),String>{if enabled{show_floating(&app)}else{if let Some(window)=app.get_webview_window("floating"){window.hide().map_err(|e|e.to_string())?}app.emit("floating-state",false).ok();Ok(())}}
#[tauri::command] fn send_budget_alert(level:u8,remaining:u8,app:AppHandle)->Result<(),String>{let title=if level<=10{"Token Manager · 预算余额严重不足"}else{"Token Manager · 预算余额提醒"};app.notification().builder().title(title).body(format!("Codex 个人预算余额约 {remaining}%，请合理安排后续任务。 ")).show().map_err(|e|e.to_string())}
#[tauri::command]
fn providers() -> Vec<AdapterCapability> { let ids=["腾讯混元","豆包（火山方舟）","文心千帆","通义百炼","智谱 AI","DeepSeek","Kimi","小米 MiMo","讯飞星火","MiniMax","阶跃星辰","零一万物","商汤日日新","百川智能","OpenAI","Anthropic","Google Gemini","自定义 OpenAI 兼容"]; ids.into_iter().map(|id| RegistryAdapter{id,billing:id=="DeepSeek"}.capability()).collect() }

/// 只检查 CC Switch 是否安装、进程是否存在，以及常用本地路由端口是否监听；不读取其密钥或供应商配置。
#[tauri::command]
fn cc_switch_status() -> CcSwitchStatus {
 let home=dirs::home_dir().unwrap_or_default();
 let local=dirs::data_local_dir().unwrap_or_default();
 let installed=[home.join(".cc-switch"),local.join("CC Switch"),local.join("cc-switch")].iter().any(|path|path.exists());
 #[cfg(windows)]
 let running=Command::new("tasklist").args(["/FO","CSV","/NH"]).output().ok().map(|output|String::from_utf8_lossy(&output.stdout).to_ascii_lowercase()).map(|text|text.contains("cc-switch")||text.contains("cc_switch")||text.contains("ccswitch")).unwrap_or(false);
 #[cfg(not(windows))]
 let running=false;
 let local_routing=[15721u16,15722,15723].into_iter().any(|port|TcpStream::connect_timeout(&SocketAddr::from(([127,0,0,1],port)),Duration::from_millis(90)).is_ok());
 let detail=if local_routing{"本地路由已连接"}else if running{"应用运行中，本地路由未检测到"}else if installed{"已安装，当前未运行"}else{"未检测到 CC Switch"}.to_string();
 CcSwitchStatus{installed:installed||running,running,local_routing,detail,checked_at:Utc::now().to_rfc3339()}
}

fn backup_key(password:&str,salt:&[u8])->[u8;32]{let mut key=[0u8;32];pbkdf2_hmac::<Sha256>(password.as_bytes(),salt,120_000,&mut key);key}

/// 导出时先用当前用户 DPAPI 解密密钥，再把整个备份用用户密码重新加密，才能安全迁移到另一台 Windows 电脑。
#[tauri::command]
fn export_encrypted_backup(path:String,password:String,ui_state:serde_json::Value,state:State<AppDb>)->Result<(),String>{
 if password.chars().count()<8{return Err("迁移密码至少需要 8 个字符".into())}
 let db=state.0.lock().map_err(|_|"数据库锁定")?;
 let mut account_query=db.prepare("SELECT id,provider,name,base_url,secret_cipher,created_at FROM account_configs ORDER BY created_at").map_err(|e|e.to_string())?;
 let accounts=account_query.query_map([],|r|Ok((r.get::<_,String>(0)?,r.get::<_,String>(1)?,r.get::<_,String>(2)?,r.get::<_,String>(3)?,r.get::<_,Vec<u8>>(4)?,r.get::<_,String>(5)?))).map_err(|e|e.to_string())?.map(|row|{let (id,provider,name,base_url,cipher,created_at)=row.map_err(|e|e.to_string())?;Ok(BackupAccount{id,provider,name,base_url,api_key:unprotect_secret(&cipher)?,created_at})}).collect::<Result<Vec<_>,String>>()?;
 let mut usage_query=db.prepare("SELECT id,provider,model,at,input_tokens,output_tokens,cached_tokens,cost,task FROM usage_events ORDER BY at").map_err(|e|e.to_string())?;
 let usage=usage_query.query_map([],|r|Ok(UsageEvent{id:r.get(0)?,provider:r.get(1)?,model:r.get(2)?,at:DateTime::parse_from_rfc3339(&r.get::<_,String>(3)?).map_err(|_|rusqlite::Error::InvalidQuery)?.with_timezone(&Utc),input:r.get::<_,i64>(4)?.max(0) as u64,output:r.get::<_,i64>(5)?.max(0) as u64,cached:r.get::<_,i64>(6)?.max(0) as u64,cost:r.get(7)?,task:r.get(8)?})).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())?;
 let mut balance_query=db.prepare("SELECT account_id,provider,currency,total_balance,granted_balance,topped_up_balance,is_available,synced_at FROM account_balances").map_err(|e|e.to_string())?;
 let balances=balance_query.query_map([],|r|Ok(AccountBalance{account_id:r.get(0)?,provider:r.get(1)?,currency:r.get(2)?,total_balance:r.get(3)?,granted_balance:r.get(4)?,topped_up_balance:r.get(5)?,is_available:r.get::<_,i64>(6)?!=0,synced_at:r.get(7)?})).map_err(|e|e.to_string())?.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())?;
 let budget=db.query_row("SELECT five_hour_limit,seven_day_limit FROM codex_budget WHERE id=1",[],|r|Ok(CodexBudget{five_hour_limit:r.get::<_,i64>(0)?.max(1) as u64,seven_day_limit:r.get::<_,i64>(1)?.max(1) as u64})).map_err(|e|e.to_string())?;drop(balance_query);drop(usage_query);drop(account_query);drop(db);
 let bundle=BackupBundle{version:1,exported_at:Utc::now().to_rfc3339(),accounts,usage,balances,five_hour_limit:budget.five_hour_limit,seven_day_limit:budget.seven_day_limit,ui_state};let plaintext=serde_json::to_vec(&bundle).map_err(|e|e.to_string())?;
 let mut salt=[0u8;16];let mut nonce=[0u8;12];rand::thread_rng().fill_bytes(&mut salt);rand::thread_rng().fill_bytes(&mut nonce);let key=backup_key(&password,&salt);let cipher=ChaCha20Poly1305::new_from_slice(&key).map_err(|e|e.to_string())?;let ciphertext=cipher.encrypt(Nonce::from_slice(&nonce),plaintext.as_ref()).map_err(|_|"无法加密迁移包")?;let envelope=BackupEnvelope{version:1,salt:BASE64.encode(salt),nonce:BASE64.encode(nonce),ciphertext:BASE64.encode(ciphertext)};fs::write(path,serde_json::to_vec(&envelope).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;Ok(())
}

#[tauri::command]
fn import_encrypted_backup(path:String,password:String,state:State<AppDb>)->Result<serde_json::Value,String>{
 let envelope:BackupEnvelope=serde_json::from_slice(&fs::read(path).map_err(|e|e.to_string())?).map_err(|_|"迁移包格式无效")?;let salt=BASE64.decode(envelope.salt).map_err(|_|"迁移包盐值无效")?;let nonce=BASE64.decode(envelope.nonce).map_err(|_|"迁移包随机数无效")?;if nonce.len()!=12{return Err("迁移包随机数长度无效".into())}let ciphertext=BASE64.decode(envelope.ciphertext).map_err(|_|"迁移包密文无效")?;let key=backup_key(&password,&salt);let cipher=ChaCha20Poly1305::new_from_slice(&key).map_err(|e|e.to_string())?;let plaintext=cipher.decrypt(Nonce::from_slice(&nonce),ciphertext.as_ref()).map_err(|_|"迁移密码错误或文件已损坏")?;let bundle:BackupBundle=serde_json::from_slice(&plaintext).map_err(|_|"迁移数据无法解析")?;
 let mut db=state.0.lock().map_err(|_|"数据库锁定")?;let tx=db.transaction().map_err(|e|e.to_string())?;tx.execute_batch("DELETE FROM account_configs;DELETE FROM usage_events;DELETE FROM account_balances;DELETE FROM balance_history;").map_err(|e|e.to_string())?;for account in bundle.accounts{let cipher=protect_secret(&account.api_key)?;tx.execute("INSERT INTO account_configs(id,provider,name,base_url,secret_cipher,created_at) VALUES(?1,?2,?3,?4,?5,?6)",params![account.id,account.provider,account.name,account.base_url,cipher,account.created_at]).map_err(|e|e.to_string())?;}for event in bundle.usage{tx.execute("INSERT INTO usage_events VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)",params![event.id,event.provider,event.model,event.at.to_rfc3339(),event.input,event.output,event.cached,event.cost,event.task]).map_err(|e|e.to_string())?;}for row in bundle.balances{tx.execute("INSERT INTO account_balances(account_id,provider,currency,total_balance,granted_balance,topped_up_balance,is_available,synced_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8)",params![row.account_id,row.provider,row.currency,row.total_balance,row.granted_balance,row.topped_up_balance,row.is_available as i32,row.synced_at]).map_err(|e|e.to_string())?;}tx.execute("UPDATE codex_budget SET five_hour_limit=?1,seven_day_limit=?2 WHERE id=1",params![bundle.five_hour_limit,bundle.seven_day_limit]).map_err(|e|e.to_string())?;tx.commit().map_err(|e|e.to_string())?;Ok(bundle.ui_state)
}
#[tauri::command]
fn save_usage(event:UsageEvent, state:State<AppDb>) -> Result<(),String> { let db=state.0.lock().map_err(|_|"数据库锁定")?; db.execute("INSERT OR REPLACE INTO usage_events VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9)",params![event.id,event.provider,event.model,event.at.to_rfc3339(),event.input,event.output,event.cached,event.cost,event.task]).map_err(|e|e.to_string())?; Ok(()) }
/// 读取本机持久化的真实 API/代理用量事件，不读取任何请求内容或密钥。
#[tauri::command]
fn list_usage(days:i64, state:State<AppDb>) -> Result<Vec<UsageEvent>,String> {
 let since=(Utc::now()-chrono::Duration::days(days.clamp(1,365))).to_rfc3339(); let db=state.0.lock().map_err(|_|"数据库锁定")?;
 let mut statement=db.prepare("SELECT id,provider,model,at,input_tokens,output_tokens,cached_tokens,cost,task FROM usage_events WHERE at>=?1 ORDER BY at DESC").map_err(|e|e.to_string())?;
 let rows=statement.query_map([since],|r|Ok(UsageEvent{id:r.get(0)?,provider:r.get(1)?,model:r.get(2)?,at:DateTime::parse_from_rfc3339(&r.get::<_,String>(3)?).map_err(|_|rusqlite::Error::InvalidQuery)?.with_timezone(&Utc),input:r.get::<_,i64>(4)?.max(0) as u64,output:r.get::<_,i64>(5)?.max(0) as u64,cached:r.get::<_,i64>(6)?.max(0) as u64,cost:r.get(7)?,task:r.get(8)?})).map_err(|e|e.to_string())?;
 rows.collect::<Result<Vec<_>,_>>().map_err(|e|e.to_string())
}
#[tauri::command]
fn parse_codex_line(line:String) -> Option<UsageEvent> { let v:serde_json::Value=serde_json::from_str(&line).ok()?; let payload=v.get("payload").unwrap_or(&v); RegistryAdapter{id:"Codex",billing:false}.normalize(payload).map(|mut e|{e.task="调试".into();e}) }
/// 只读访问 Codex 自己的状态库；仅提取计数及更新时间，绝不读取提示词或会话正文。
#[tauri::command]
fn codex_snapshot() -> Result<CodexSnapshot, String> {
 let path=dirs::home_dir().ok_or("无法定位用户目录")?.join(".codex").join("state_5.sqlite");
 if !path.exists() { return Err("未发现 Codex 本地状态库".into()); }
 let db=Connection::open_with_flags(path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|e|e.to_string())?;
 let (total, active, updated):(i64,i64,i64)=db.query_row(
  "SELECT COALESCE(SUM(tokens_used),0), COALESCE((SELECT tokens_used FROM threads ORDER BY updated_at_ms DESC LIMIT 1),0), COALESCE(MAX(NULLIF(updated_at_ms,0)),MAX(updated_at)*1000,0) FROM threads",
  [], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?))
 ).map_err(|e| format!("无法读取 Codex 用量：{e}"))?;
 Ok(CodexSnapshot { total_tokens:total.max(0) as u64, active_thread_tokens:active.max(0) as u64, updated_at_ms:updated, source:"Codex 本地状态库（threads.tokens_used）".into() })
}
fn current_budget(state:&State<AppDb>) -> Result<CodexBudget,String> {
 let db=state.0.lock().map_err(|_|"数据库锁定")?;
 db.query_row("SELECT five_hour_limit,seven_day_limit FROM codex_budget WHERE id=1",[],|r|Ok(CodexBudget{five_hour_limit:r.get::<_,i64>(0)?.max(1) as u64,seven_day_limit:r.get::<_,i64>(1)?.max(1) as u64})).map_err(|e|e.to_string())
}
#[tauri::command]
fn save_codex_budget(five_hour_limit:u64, seven_day_limit:u64, state:State<AppDb>) -> Result<CodexBudget,String> {
 if five_hour_limit==0 || seven_day_limit==0 { return Err("预算必须大于 0".into()); }
 let db=state.0.lock().map_err(|_|"数据库锁定")?;
 db.execute("UPDATE codex_budget SET five_hour_limit=?1,seven_day_limit=?2 WHERE id=1",params![five_hour_limit as i64,seven_day_limit as i64]).map_err(|e|e.to_string())?;
 Ok(CodexBudget{five_hour_limit,seven_day_limit})
}
fn field(body:&str, marker:&str)->Option<String>{ let start=body.find(marker)?+marker.len(); let value=&body[start..]; Some(value.chars().take_while(|c|c.is_ascii_alphanumeric()||*c=='-'||*c=='_'||*c=='.'||*c==':').collect()) }
/// 返回最近七天每个 Codex turn 的最终 token 计数，供本地柱状图使用。
#[tauri::command]
fn codex_usage_series() -> Result<Vec<CodexUsagePoint>,String> {
 let path=dirs::home_dir().ok_or("无法定位用户目录")?.join(".codex").join("logs_2.sqlite");
 if !path.exists(){return Err("未发现 Codex 日志数据库".into());}
 let since=Utc::now().timestamp()-7*24*3600;
 let db=Connection::open_with_flags(path,rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|e|e.to_string())?;
 let mut query=db.prepare("SELECT ts,feedback_log_body FROM logs WHERE ts>=?1 AND feedback_log_body LIKE '%total_usage_tokens=%'").map_err(|e|e.to_string())?;
 let rows=query.query_map([since],|r|Ok((r.get::<_,i64>(0)?,r.get::<_,Option<String>>(1)?))).map_err(|e|e.to_string())?;
 let mut turns:HashMap<String,CodexUsagePoint>=HashMap::new();
 for row in rows {let (ts,body)=row.map_err(|e|e.to_string())?;let Some(body)=body else{continue};let Some(id)=field(&body,"turn_id=") else{continue};let Some(tokens)=field(&body,"total_usage_tokens=").and_then(|v|v.parse::<u64>().ok()) else{continue};let model=field(&body,"model=").unwrap_or_else(||"Codex".into());let lower=body.to_ascii_lowercase();let category=if lower.contains("task_type=generation")||lower.contains("intent=create"){"全新生成"}else if lower.contains("task_type=explain")||lower.contains("intent=explain"){"问答解释"}else if lower.contains("task_type=debug")||lower.contains("intent=fix"){"修改调试"}else if tokens>=30_000{"全新生成"}else if tokens<=8_000{"问答解释"}else{"修改调试"}.to_string();let temperature=field(&body,"temperature=").and_then(|v|v.parse::<f64>().ok());let replace=turns.get(&id).map(|old|tokens>old.tokens||ts>old.at).unwrap_or(true);if replace{turns.insert(id.clone(),CodexUsagePoint{at:ts,tokens,model,session_id:id,category,temperature});}}
 let mut points=turns.into_values().collect::<Vec<_>>();points.sort_by_key(|point|point.at);Ok(points)
}
/// 每个 turn 取最终的最大 total_usage_tokens，避免流式日志多次累计造成重复计数。
#[tauri::command]
fn codex_window_usage(state:State<AppDb>) -> Result<CodexWindowUsage,String> {
 let path=dirs::home_dir().ok_or("无法定位用户目录")?.join(".codex").join("logs_2.sqlite");
 if !path.exists(){return Err("未发现 Codex 日志数据库".into());}
 let now=Utc::now().timestamp(); let week_start=now-7*24*3600; let short_start=now-5*3600;
 let db=Connection::open_with_flags(path,rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY).map_err(|e|e.to_string())?;
 let mut query=db.prepare("SELECT ts,feedback_log_body FROM logs WHERE ts>=?1 AND feedback_log_body LIKE '%post sampling token usage%'").map_err(|e|e.to_string())?;
 let rows=query.query_map([week_start],|r|Ok((r.get::<_,i64>(0)?,r.get::<_,Option<String>>(1)?))).map_err(|e|e.to_string())?;
 let mut turns: HashMap<String, (i64, u64)> = HashMap::new();
 for row in rows { let (ts,body)=row.map_err(|e|e.to_string())?; let Some(body)=body else{continue}; let Some(id)=field(&body,"turn_id=") else{continue}; let Some(tokens)=field(&body,"total_usage_tokens=").and_then(|v|v.parse::<u64>().ok()) else{continue}; let entry=turns.entry(id).or_insert((ts,tokens)); if tokens>entry.1 || ts>entry.0 {*entry=(ts,tokens)} }
 let mut five=0;let mut seven=0;for (_, (ts,tokens)) in turns {seven+=tokens;if ts>=short_start{five+=tokens}}
 Ok(CodexWindowUsage{five_hour_used:five,seven_day_used:seven,budget:current_budget(&state)?,source:"Codex 本地日志（每个 turn 最终 token 计数）".into()})
}
#[cfg(test)]
mod tests {
 use super::*;
 #[test]
 fn parses_deepseek_stream_usage(){let body=b"data: {\"choices\":[{\"delta\":{}}],\"usage\":{\"prompt_tokens\":1000,\"completion_tokens\":200,\"prompt_cache_hit_tokens\":800}}\n\ndata: [DONE]\n";let values=usage_values(body);assert_eq!(usage_counts(&values[0]),Some((1000,200,800)));}
 #[test]
 fn parses_anthropic_and_gemini_usage(){let anthropic=serde_json::json!({"usage":{"input_tokens":120,"output_tokens":30,"cache_read_input_tokens":80}});assert_eq!(usage_counts(&anthropic),Some((120,30,80)));let gemini=serde_json::json!({"usageMetadata":{"promptTokenCount":500,"candidatesTokenCount":70,"thoughtsTokenCount":20,"cachedContentTokenCount":300}});assert_eq!(usage_counts(&gemini),Some((500,90,300)));}
 #[test]
 fn calculates_v4_pro_cny_cost(){let cost=deepseek_cost("deepseek-v4-pro",1_000_000,1_000_000,200_000);assert!((cost-8.405).abs()<0.000001);}
 #[test]
 fn calculates_versioned_provider_cost(){let cost=provider_cost("小米 MiMo","mimo-v2.5-pro",1_000_000,500_000,200_000);assert!((cost-2.32).abs()<0.000001);assert_eq!(provider_cost("自定义 OpenAI 兼容","unknown",10,10,0),0.0);}
}
pub fn run() {
 tauri::Builder::default().plugin(tauri_plugin_dialog::init()).plugin(tauri_plugin_notification::init()).plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, None)).plugin(tauri_plugin_opener::init()).manage(AppDb::open()).manage(ProxyServerState(Mutex::new(HashMap::new()))).setup(|app| {
  let show=MenuItem::with_id(app,"show","显示主窗口",true,None::<&str>)?;let floating=MenuItem::with_id(app,"floating","开启悬浮窗",true,None::<&str>)?;let close_floating=MenuItem::with_id(app,"close_floating","关闭悬浮窗",true,None::<&str>)?;let hide=MenuItem::with_id(app,"hide","最小化到托盘",true,None::<&str>)?;let quit=MenuItem::with_id(app,"quit","退出",true,None::<&str>)?;let menu=Menu::with_items(app,&[&show,&floating,&close_floating,&hide,&quit])?;
  TrayIconBuilder::with_id("tray").menu(&menu).on_menu_event(|app,event| match event.id().as_ref(){"show"=>{if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}},"floating"=>{let _=show_floating(app);},"close_floating"=>{if let Some(w)=app.get_webview_window("floating"){let _=w.hide();}app.emit("floating-state",false).ok();},"hide"=>{if let Some(w)=app.get_webview_window("main"){let _=w.hide();}},"quit"=>app.exit(0),_=>{}}).build(app)?;if let Some(main)=app.get_webview_window("main"){let main_copy=main.clone();main.on_window_event(move|event|if let WindowEvent::CloseRequested{api,..}=event{api.prevent_close();let _=main_copy.hide();});}if std::env::args().any(|arg|arg=="--floating"){show_floating(app.handle())?;if let Some(main)=app.get_webview_window("main"){let _=main.hide();}}Ok(())
 }).invoke_handler(tauri::generate_handler![providers,save_usage,list_usage,parse_codex_line,codex_snapshot,codex_window_usage,codex_usage_series,save_codex_budget,save_account_config,list_account_configs,delete_account_config,clear_account_configs,sync_account_balances,list_account_balances,list_balance_history,fetch_account_models,cc_switch_status,export_encrypted_backup,import_encrypted_backup,set_floating_window,send_budget_alert,start_proxy,start_all_proxies]).run(tauri::generate_context!()).expect("运行 Token Manager 失败");
}

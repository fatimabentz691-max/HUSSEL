# Token Manager 数据来源说明

Token Manager 将“模型调用接口”和“账户账单接口”分开处理。能够使用模型 API，并不代表该密钥同时拥有余额或组织账单权限。

## 所有已配置平台的统一监控

所有平台均可通过本地代理记录以下数据：

- API 请求次数、成功与失败状态；
- 输入 Token、输出 Token、缓存命中 Token；
- 请求时间、平台和模型；
- 7 天趋势、最近请求和账单导出。

代理不保存请求或响应正文。只有厂商响应实际返回 usage 字段时，Token 才会记为非零；没有 usage 的失败响应仍会计入请求次数。

当前已验证的响应格式包括 OpenAI/OpenAI 兼容、Anthropic、Google Gemini 和 DeepSeek。其他国产 OpenAI 兼容接口复用统一解析器。

## 余额与官方账单

| 平台类型 | 当前余额来源 | 说明 |
| --- | --- | --- |
| DeepSeek | 官方 `/user/balance` | 使用普通 DeepSeek API Key，可同步人民币总余额、充值余额和赠送余额 |
| OpenAI、Anthropic | 暂不使用普通模型 Key 查询余额 | 组织 Usage/Costs 接口通常要求管理员级密钥，与普通模型 Key 权限不同 |
| Google Gemini | 本地代理 | Cloud Billing 需要独立 Google Cloud IAM 和账单账号，不等同于 Gemini API Key |
| 国内云平台 | 本地代理或账单导入 | 多数账单接口要求云账号 AK/SK、签名、地域和账单权限，不能把模型 API Key 当成账单凭据 |
| 第三方 OpenAI 兼容服务 | 本地代理 | 是否存在余额接口由中转服务自行决定 |

界面必须明确显示数据来源；没有已验证官方接口时，不显示伪造的实时余额。


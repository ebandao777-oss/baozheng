> 公共复用模块，被模块A和模块C引用。
> 数据源：flk.npc.gov.cn 官方 API。API 不可用时明确告知用户，不做降级。

## A7. 混合法条检索引擎

本Skill采用 **API 优先** 的法条检索策略。API 不可用时明确告知用户，建议访问 flk.npc.gov.cn 手动查询，不做降级到非官方源。

### 7.1 架构总览

```
用户输入关键词
  → 调用国家法律法规数据库官方 API（flk.npc.gov.cn/api/）
  → 返回结果 → 格式化输出：📜法律条文 + ⚖️参考案例（如有）
  → API 不可用 → 明确告知用户，建议访问 flk.npc.gov.cn 手动查询
```

### 7.2 官方API查询

在AI运行环境具备公网HTTP访问能力时，调用国家法律法规数据库官方接口进行查询。

**API 端点：** `https://flk.npc.gov.cn/api/`

**Query 参数：**
- `type`: `flfg`（固定值，法律法规）
- `searchType`: `title;vague`（模糊匹配标题）
- `keyword`: 查询关键词
- `page`: `1`, `size`: `5`

**超时策略：** 8 秒超时，默认返回 5 条结果。

#### 可执行调用代码

```python
import urllib.parse
import json

def query_law_api(keyword: str) -> dict:
    """
    调用 flk.npc.gov.cn 官方 API 检索法条。
    返回: {"success": bool, "results": [...], "error": str|None}
    """
    params = {
        "type": "flfg",
        "searchType": "title;vague",
        "keyword": keyword,
        "page": "1",
        "size": "5",
    }
    url = "https://flk.npc.gov.cn/api/?" + urllib.parse.urlencode(params)

    try:
        # 调用 web_fetch 工具（主 Agent 提供），8 秒超时
        # 注意：此处为伪代码模板，实际执行时由 Agent 调用 web_fetch(url=url, backend='httpx')
        response = web_fetch(url=url, backend='httpx')
        data = json.loads(response)
        return {"success": True, "results": data.get("result", {}).get("data", []), "error": None}
    except Exception as e:
        return {"success": False, "results": [], "error": str(e)}
```

**实际执行指令（Agent 执行时照此操作）：**

1. 拼接 URL：`https://flk.npc.gov.cn/api/?type=flfg&searchType=title;vague&keyword={关键词}&page=1&size=5`
2. 调用 `web_fetch(url=<URL>, backend='httpx')`，超时 8 秒
3. 解析返回 JSON → `result.data[]` 字段含法律名称、条文号、条文原文
4. 若 `web_fetch` 失败或返回空数组 → 明确告知用户 API 不可用，建议直接访问 https://flk.npc.gov.cn 查询，不做降级到本地知识库

API 返回的数据（法律名称、公布日期、施行日期、条文内容）以官方来源为准。

### 7.3 API 不可用时的处理

当官方 API 不可用时，不做降级到任何非官方源的操作。处理方式：
- 明确告知用户：「国家法律法规数据库 API 当前不可用，建议直接访问 https://flk.npc.gov.cn 手动查询。」
- 不得使用内建知识库、本地缓存或任何非官方数据源替代。

### 7.4 统一引用格式

所有法条引用均按统一格式输出：
- 《**法律全称**》\"**第XXX条** 法条原文内容\"
- ⚠️ 法条引用末尾附带说明：\"以上内容仅供参考，具体适用请以官方最新文本及司法实践为准\"

### 7.5 查询示例

通过官方 API 查询的常见问题：
```
用户："劳动法对试用期怎么规定的？"
输出：📜 查询到《中华人民共和国劳动合同法》第十九条：……（来自 flk.npc.gov.cn 官方 API）
```

### 7.6 局限性说明

以下情况如 API 不可用，不做降级处理，明确告知用户并建议访问官方渠道：
- 涉及具体司法案例裁判观点的
- 涉及地方性法规、部门规章的
- 需要进行法条对比分析的
- 需要最新修正案具体条款的

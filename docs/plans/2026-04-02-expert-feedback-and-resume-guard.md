# Expert Feedback And Resume Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Expert 对话增加问题反馈闭环、免工具续写守门和澄清交互修复，并提供 `Admin` 反馈后台。

**Architecture:** 后端以 `expert_chat.duckdb` 为中心扩展反馈表、管理员接口和 `resume` 完整性检查；前端在 Expert 对话页增加消息级反馈入口、检查并继续流程和澄清交互状态修复；通过后端 pytest 和前端 `node:test` 双向兜底回归。实现优先遵守 TDD、单一职责和最小改动原则。

**Tech Stack:** FastAPI, DuckDB, Pydantic, Loguru, Next.js 15, React 19, Zustand, Node `node:test`, pytest

---

### Task 1: 写设计与计划文档

**Files:**
- Create: `docs/plans/2026-04-02-expert-feedback-and-resume-guard-design.md`
- Create: `docs/plans/2026-04-02-expert-feedback-and-resume-guard.md`

**Step 1: 写设计文档**

把已确认的范围写入设计稿，覆盖：

- 默认 `Admin / WeigongAdmin`
- `expert.feedback_reports`
- `resume` 完整性检查
- 消息级反馈
- 澄清单选确认、空选项兜底、子选项取消

**Step 2: 写实施计划**

把实现拆成后端、前端、测试三条线，并明确每个任务涉及的文件。

**Step 3: 保存文档**

确认两个文件路径正确：

- `docs/plans/2026-04-02-expert-feedback-and-resume-guard-design.md`
- `docs/plans/2026-04-02-expert-feedback-and-resume-guard.md`

**Step 4: 提交文档**

Run:

```bash
git add docs/plans/2026-04-02-expert-feedback-and-resume-guard-design.md docs/plans/2026-04-02-expert-feedback-and-resume-guard.md
git commit -m "docs: add expert feedback and resume guard design"
```

Expected: 仅 docs 文件被提交，不包含其他工作中的代码改动。

### Task 2: 后端管理员与反馈存储

**Files:**
- Modify: `backend/auth.py`
- Modify: `backend/main.py`
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试，覆盖管理员初始化与反馈写入**

在 `tests/unit/expert/test_routes.py` 新增测试：

```python
def test_default_admin_is_bootstrapped():
    ...

def test_feedback_report_is_persisted_with_full_context():
    ...

def test_feedback_admin_endpoint_requires_admin_user():
    ...
```

**Step 2: 运行测试，确认失败原因正确**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "admin or feedback" -v
```

Expected: 因默认管理员、反馈表或接口尚不存在而失败。

**Step 3: 写最小实现**

- 在 `backend/auth.py` 增加 `ensure_default_admin()`，固定创建 `Admin / WeigongAdmin`
- 在 `backend/main.py` 启动时调用
- 在 `backend/engine/expert/routes.py` 初始化 `expert.feedback_reports`
- 新增提交反馈、查看反馈列表、查看详情、标记处理接口
- 在 `backend/engine/expert/schemas.py` 增加反馈请求/响应模型

**Step 4: 运行测试，确认通过**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py -k "admin or feedback" -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add backend/auth.py backend/main.py backend/engine/expert/routes.py backend/engine/expert/schemas.py tests/unit/expert/test_routes.py
git commit -m "feat: add expert feedback storage and admin bootstrap"
```

### Task 3: 后端 resume 完整性检查守门

**Files:**
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_agent.py`
- Test: `tests/unit/expert/test_routes.py`

**Step 1: 写失败测试，覆盖“已完整不续写”和“不完整才续写”**

在测试中加入两个场景：

```python
async def test_resume_marks_message_completed_when_completion_check_says_complete():
    ...

async def test_resume_calls_resume_reply_when_completion_check_says_incomplete():
    ...
```

**Step 2: 运行测试，确认失败**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py -k "resume and complete" -v
```

Expected: 因尚无完整性检查逻辑而失败。

**Step 3: 写最小实现**

- 在 `backend/engine/expert/agent.py` 增加无工具完整性检查方法，使用 `chat_stream()` 收集结构化 JSON
- 在 `backend/engine/expert/routes.py` 升级 `/api/v1/expert/chat/resume`：
  - 先做检查
  - `is_complete=true` 时直接更新消息为 `completed`
  - `is_complete=false` 时才继续 `resume_reply`
- 为 `completed` 但疑似截断的消息预留可选检查入口参数

**Step 4: 运行测试，确认通过**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py -k "resume and complete" -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/expert/agent.py backend/engine/expert/routes.py backend/engine/expert/schemas.py tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py
git commit -m "feat: add expert resume completion guard"
```

### Task 4: 澄清后端兜底与状态约束

**Files:**
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/schemas.py`
- Test: `tests/unit/expert/test_routes.py`
- Test: `tests/unit/expert/test_agent.py`

**Step 1: 写失败测试，覆盖空选项不能自动推进**

新增测试：

```python
async def test_clarify_true_without_options_falls_back_to_safe_options():
    ...
```

**Step 2: 运行测试，确认失败**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py -k "clarify and options" -v
```

Expected: 因当前允许空选项或直接推进而失败。

**Step 3: 写最小实现**

- 在 `backend/engine/expert/agent.py` 中对 `should_clarify=true + options=[]` 增加后端兜底
- 保底输出至少 3 个可选方向和 `skip_option`
- 保持 `needs_more`、`multi_select` 与 persona 语义一致

**Step 4: 运行测试，确认通过**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py -k "clarify and options" -v
```

Expected: PASS

**Step 5: 提交**

```bash
git add backend/engine/expert/agent.py backend/engine/expert/schemas.py tests/unit/expert/test_agent.py tests/unit/expert/test_routes.py
git commit -m "fix: add safe fallback for empty clarification options"
```

### Task 5: 前端反馈入口与管理员页面

**Files:**
- Modify: `frontend/types/expert.ts`
- Modify: `frontend/stores/useExpertStore.ts`
- Modify: `frontend/components/expert/MessageBubble.tsx`
- Modify: `frontend/components/ui/NavSidebar.tsx`
- Modify: `frontend/app/expert/page.tsx`
- Create: `frontend/app/admin/feedback/page.tsx`
- Create: `frontend/lib/expertFeedback.test.ts`

**Step 1: 写失败测试，覆盖反馈 payload 组装**

创建测试：

```ts
import test from "node:test";
import assert from "node:assert/strict";

test("builds expert feedback payload with full message context", () => {
  const payload = buildExpertFeedbackPayload(...);
  assert.equal(payload.issue_type, "llm_truncated");
  assert.ok(payload.context_json.history.length > 0);
});
```

**Step 2: 运行测试，确认失败**

Run:

```bash
node --test frontend/lib/expertFeedback.test.ts
```

Expected: 因 helper 或 payload 尚未实现而失败。

**Step 3: 写最小实现**

- 在 `frontend/types/expert.ts` 增加反馈类型和恢复结果类型
- 在 `frontend/stores/useExpertStore.ts` 增加提交反馈、提交并检查续写、后台列表读取动作
- 在 `frontend/components/expert/MessageBubble.tsx` 增加红色三角反馈入口
- 在 `frontend/components/ui/NavSidebar.tsx` 中仅对 `Admin` 显示反馈后台导航
- 新建 `frontend/app/admin/feedback/page.tsx`

**Step 4: 运行测试，确认通过**

Run:

```bash
node --test frontend/lib/expertFeedback.test.ts
```

Expected: PASS

**Step 5: 提交**

```bash
git add frontend/types/expert.ts frontend/stores/useExpertStore.ts frontend/components/expert/MessageBubble.tsx frontend/components/ui/NavSidebar.tsx frontend/app/expert/page.tsx frontend/app/admin/feedback/page.tsx frontend/lib/expertFeedback.test.ts
git commit -m "feat: add expert feedback reporting UI and admin page"
```

### Task 6: 前端澄清选择状态机修复

**Files:**
- Modify: `frontend/components/expert/MessageBubble.tsx`
- Modify: `frontend/stores/useExpertStore.ts`
- Modify: `frontend/types/expert.ts`
- Create: `frontend/lib/clarificationSelection.test.ts`

**Step 1: 写失败测试，覆盖单选确认与子选项取消**

创建测试：

```ts
import test from "node:test";
import assert from "node:assert/strict";

test("single select does not auto submit before confirm", () => {
  ...
});

test("clicking the same sub choice toggles it off", () => {
  ...
});
```

**Step 2: 运行测试，确认失败**

Run:

```bash
node --test frontend/lib/clarificationSelection.test.ts
```

Expected: 因当前交互即时提交、无法取消而失败。

**Step 3: 写最小实现**

- 把单选和多选统一为“先选后确认”
- 子选项支持二次点击取消
- 父选项仅负责展开/折叠
- 前端不再在空选项场景自动推进到 chat

**Step 4: 运行测试，确认通过**

Run:

```bash
node --test frontend/lib/clarificationSelection.test.ts
```

Expected: PASS

**Step 5: 提交**

```bash
git add frontend/components/expert/MessageBubble.tsx frontend/stores/useExpertStore.ts frontend/types/expert.ts frontend/lib/clarificationSelection.test.ts
git commit -m "fix: repair expert clarification selection flow"
```

### Task 7: 回归验证与收尾

**Files:**
- Modify: `tests/unit/expert/test_routes.py`
- Modify: `tests/unit/expert/test_agent.py`
- Modify: `frontend/lib/expertFeedback.test.ts`
- Modify: `frontend/lib/clarificationSelection.test.ts`

**Step 1: 跑后端回归**

Run:

```bash
backend/.venv/bin/python -m pytest tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py -v
```

Expected: PASS

**Step 2: 跑前端回归**

Run:

```bash
node --test frontend/lib/expertFeedback.test.ts frontend/lib/clarificationSelection.test.ts
```

Expected: PASS

**Step 3: 检查变更范围**

Run:

```bash
git diff --stat
```

Expected: 只包含本计划涉及的后端、前端、测试与文档文件。

**Step 4: 记录人工验证建议**

补一段简短手工验证清单：

- 登录 `Admin / WeigongAdmin`
- 普通用户提交反馈
- `Admin` 查看并处理反馈
- Expert 单选确认
- 子选项取消
- 中断消息检查并继续

**Step 5: 提交**

```bash
git add tests/unit/expert/test_routes.py tests/unit/expert/test_agent.py frontend/lib/expertFeedback.test.ts frontend/lib/clarificationSelection.test.ts
git commit -m "test: add regression coverage for expert feedback and resume guard"
```

# Parallel Planning Convention

> 目的：为多终端 / 多 worktree 并行开发建立统一计划格式，减少任务执行阶段的临时拆分和写集冲突。

---

## 1. 何时必须用并行计划

满足任一条件时，计划不应只写单线程主线，而应默认输出并行执行结构：

- 任务预计涉及 4 个以上文件
- 任务横跨后端 / 前端 / 测试 / 文档中的两个以上区域
- 任务目标本身天然可拆分为不同职责层
- 用户明确希望提高并行度
- 存在独立的 write path / read path / UI path

---

## 2. 每份大计划必须包含三部分

### A. Mainline Plan

说明：

- 总目标
- 阶段顺序
- 架构边界
- 哪些任务必须串行

它回答的是：

- 这件事总体要做成什么样
- 哪些东西不能乱改
- 并行任务最后要收敛到哪套模型

### B. Worker Plans

至少拆成 2 份，理想情况下 3 份。

每个 worker plan 必须明确：

- **负责文件**
- **禁止触碰文件**
- **测试文件**
- **完成标准**
- **是否允许提交独立 commit**

它回答的是：

- 这个终端该改什么
- 这个终端绝对不要改什么
- 完成后怎样判断可以交给 review

### C. Review / Integration Plan

必须写明：

- 谁负责 review
- 哪些提交可以独立 review
- 什么时候开始集成
- 集成时跑哪些回归测试

它回答的是：

- 不是每个 worker 自己宣称完成，而是谁来最终验收

---

## 3. 推荐拆分方式

优先使用“写集不重叠”的拆分，而不是按功能名随意拆。

### 模式 1：Schema / Runtime / Frontend

适用：

- 有数据库 / API / 页面三层

拆分：

- Worker A：schema + models + migration + schema tests
- Worker B：runtime / orchestration / service / execution
- Worker C：frontend / read model / UI components

### 模式 2：Write Path / Read Path / UI

适用：

- 系统已经具备写链路和读链路分离潜力

拆分：

- Worker A：写路径（command side）
- Worker B：读路径（query side）
- Worker C：前端或接入层

### 模式 3：Infrastructure / Domain / Product Surface

适用：

- 既有底层升级，又有业务逻辑，又有用户可见改动

拆分：

- Worker A：基础设施
- Worker B：领域逻辑
- Worker C：页面/API/外部接入

---

## 4. 强制规则

### 4.1 Worker 必须有 disjoint write set

如果两个 worker 都需要频繁改同一个文件，就不算合格并行拆分。

遇到这种情况，必须：

- 重划边界
- 或先抽一层文件，再拆 worker

### 4.2 测试也要尽量拆开

不要默认所有 worker 都继续往同一个测试文件里堆。

优先策略：

- 每个 worker 建自己的测试文件
- 公共测试文件只允许一个 worker 持有

### 4.3 设计未收敛前，不做高冲突并行

如果对象模型和边界还没定住，不要强行开多个终端同时实现主线代码。

先做：

- architecture / design convergence

再做：

- 多 worker 实现

### 4.4 Review 角色不能缺失

并行计划至少要有一个“集成 / review 位”。

否则会出现：

- 每个 worker 看起来都完成了
- 但整体架构已经偏离

---

## 5. 推荐的计划结构模板

```md
# [Feature] Implementation Plan

## Mainline

- Goal:
- Architecture boundary:
- Serial dependencies:
- Non-goals:

## Worker A — [Name]

- Owns:
- Must not touch:
- Tests:
- Done when:

## Worker B — [Name]

- Owns:
- Must not touch:
- Tests:
- Done when:

## Worker C — [Name]

- Owns:
- Must not touch:
- Tests:
- Done when:

## Review / Integration

- Reviewer:
- Integration owner:
- Required regression tests:
- Merge order:
```

---

## 6. 对 Main Agent 这类任务的默认拆法

以后再写类似 Main Agent / 多层系统改造计划，默认优先用下面的三终端结构：

- Worker A：Schema / state / review-memory 基础设施
- Worker B：brain / execution / orchestration 写路径
- Worker C：frontend read model / dashboard / API 消费层

Review 位单独保留，不参与高冲突写入。

---

## 7. 判断一个并行计划是否合格

只要满足以下 5 条，就算合格：

- 总目标和边界写清楚了
- 至少拆出 2-3 个 worker
- 每个 worker 的禁止修改范围清楚
- 测试归属清楚
- 明确谁来收口 review

如果缺任何一条，就不要进入执行。

---

## 8. 结论

以后默认不再写“单线程再临时拆分”的计划。

标准做法是：

1. 先写主线架构
2. 再写多 worker 并行任务
3. 最后写 review / integration 收口方式

并行不是执行时加速，而是计划阶段就设计出来。

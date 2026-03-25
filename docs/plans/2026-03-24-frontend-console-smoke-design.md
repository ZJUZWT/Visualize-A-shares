# Frontend Console Smoke Design

**Date:** 2026-03-24

## Goal

为 `frontend/` 增加一层自动化“页面打开即检查”的冒烟测试，重点发现主页面加载后的前端控制台报错，而不是验证完整业务链路。

## Scope

首批覆盖主路由：

- `/`
- `/expert`
- `/debate`
- `/agent`
- `/sector`
- `/plans`
- `/tasks`

检测目标：

- `console.error`
- `pageerror`
- 页面首屏加载时的未捕获异常

暂不纳入：

- 真实后端联调
- 复杂用户交互回归
- 视觉回归
- 接口数据正确性验证

## Recommended Approach

使用 Playwright 做前端 smoke test，但把 `/api/**` 统一 mock 成最小可渲染数据，让测试只回答一个问题：页面打开后，前端自己会不会报错。

这样做的原因：

- 比 `next build` 更接近真实浏览器运行时
- 比连真实后端更稳定
- 失败信号明确，适合持续跑

## Test Strategy

每个页面测试流程保持一致：

1. 打开页面
2. 监听并收集 `console.error`
3. 监听并收集 `pageerror`
4. 等待页面出现稳定锚点
5. 断言没有前端运行时错误

为了避免噪音，mock 层只返回页面渲染必须的数据结构，不扩展成业务级假后端。

## Architecture

- 在 `frontend/` 下新增 Playwright 配置
- 新增一个公共 smoke helper，统一安装错误监听和 API mock
- 新增一组主路由 smoke tests
- 在 `package.json` 中提供一条标准入口命令，便于本地和 CI 复用

## Verification

最低验收标准：

- `next build` 继续通过
- 主路由 smoke tests 可执行
- 访问上述 7 个页面时，测试会在存在 `console.error` 或 `pageerror` 时失败

## Constraints

- 当前工作区内尚未直接安装 `@playwright/test`
- 如果本地依赖不可直接使用，需要先补 devDependency 和脚本，再验证是否可运行

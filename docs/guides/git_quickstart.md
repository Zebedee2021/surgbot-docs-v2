# Git 快速入门

## 基本工作流

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/surgbot-docs.git
cd surgbot-docs

# 2. 创建功能分支
git checkout -b docs/perception-update

# 3. 修改文档后提交
git add docs/modules/perception/index.md
git commit -m "docs(perception): 更新夹取点算法当前状态"

# 4. 推送并创建 PR
git push origin docs/perception-update
```

## 提交规范

格式：`类型(模块): 简短描述`

```
feat(perception): 添加夹取点修正算法
fix(nlp): 修复词库匹配大小写问题
docs(sim2real): 更新第二级验证 checklist
chore: 更新依赖版本
```

## 分支规范

- `main`：稳定版本，直接对应 GitHub Pages
- `docs/xxx`：文档更新
- `feat/xxx`：功能开发
- `fix/xxx`：问题修复

<div class="doc-footer">
  <span>最近更新 2026-03-18</span>
</div>

# Sim2Real 验证状态面板

> 代码从开发到上真机须完整通过三级验证。本页每周更新一次。

---

## 三级验证进度

<div class="sim2real-panel">

<div class="tier-track">
  <div class="tier-step">
    <div class="tier-circle done">✓</div>
    <div class="tier-name">第一级<br>LIBERO + MuJoCo</div>
    <div class="tier-sub">决策模型验证</div>
  </div>
  <div class="tier-connector done-wip"></div>
  <div class="tier-step">
    <div class="tier-circle wip">⋯</div>
    <div class="tier-name">第二级<br>Isaac Sim</div>
    <div class="tier-sub">全流程闭环仿真</div>
  </div>
  <div class="tier-connector wip-q"></div>
  <div class="tier-step">
    <div class="tier-circle queued">3</div>
    <div class="tier-name">第三级<br>真实 CR5AF</div>
    <div class="tier-sub">实验室 → 医院</div>
  </div>
</div>

</div>

---

## 第一级：LIBERO + MuJoCo <span class="status-done">已跑通</span>

**技术栈：** `robosuite` · `MuJoCo` · `PyTorch` · `OpenVLA` · `flash-attn` · `GLX/EGL`

**验证范围：** 决策逻辑 · 动作序列正确性（不涉及真实传感器和硬件）

| 检查项 | 状态 |
|--------|------|
| 环境安装配置通过 | ✅ 完成 |
| OpenVLA 权重加载成功 | ✅ 完成 |
| LIBERO 数据集正确读取 | ✅ 完成 |
| `run_libero_eval.py` 脚本可运行 | ✅ 完成 |
| `libero_spatial` 10 个任务可评测 | ✅ 完成 |
| 排查稳定性 bug，建立可复现基线 | 🔄 进行中 |
| 形成可复现安装文档 | ⭕ 待完成 |

---

## 第二级：Isaac Sim + Omniverse <span class="status-wip">搭建中</span>

**技术栈：** `Isaac Sim` · `Omniverse Nucleus` · `ROS2 Bridge` · `MoveIt!` · `Python SDK`

**验证范围：** 感知 + 决策 + 执行完整闭环 · 碰撞检测 · 力控 · 状态机全流程

| 检查项 | 状态 |
|--------|------|
| Isaac Sim 安装 + 基础场景启动 | ✅ 完成 |
| CR5 URDF 导入 + 双指夹爪配置 | 🔄 进行中 |
| 手术室布局建模（床 · 台 · 托盘） | 🔄 进行中 |
| RGB-D / ToF 传感器仿真配置 | ⭕ 待完成 |
| 手眼标定（仿真版）流程跑通 | ⭕ 待完成 |
| 状态机全流程联调（待机→执行→复位） | ⭕ 待完成 |
| 碰撞检测 + 力控验证 | ⭕ 待完成 |
| 仿真数据采集 → 模型微调 | ⭕ 待完成 |

!!! tip "进入下一级的门槛"
    第二级验证通过的标准见下方"目标指标"表，五项指标全部达标后方可推进第三级。

---

## 第三级：真实 CR5AF 机械臂 <span class="status-wip">改进中</span>

**技术栈：** `Dobot SDK (TCP)` · `越疆 CR5AF` · 双目摄像头 · 力反馈夹爪

**验证范围：** 实验室功能测试 → 医院现场验证

| 检查项 | 状态 |
|--------|------|
| 首轮现场测试（宣武医院 2026.02）| ✅ 完成，详见[现场测试报告](../progress/field_test_202602.md) |
| 手眼标定半自动化（问题 #1）| 🔄 进行中 |
| 夹取点修正算法（问题 #3 #4）| 🔄 进行中 |
| 语音识别延迟优化 ≤1s（问题 #9）| 🔄 进行中 |
| GUI 参数配置界面（问题 #2）| ⭕ 待完成 |
| Z 轴高度自适应补偿（问题 #3）| ⭕ 待完成 |
| 多级安全校验（问题 #8）| ⭕ 待完成 |
| 二维码双验证机制（问题 #6）| ⭕ 规划中 |

---

## Sim Gap 追踪

仿真与真机之间的已知差距，是 sim2real 迁移的核心风险项。

<div class="sim2real-panel">

<table class="sim-gap-table">
<thead>
<tr>
  <th style="width:16%">差距项</th>
  <th style="width:10%">风险</th>
  <th style="width:37%">现象描述</th>
  <th style="width:37%">对齐方案 / 状态</th>
</tr>
</thead>
<tbody>
<tr>
  <td>手眼标定误差</td>
  <td><span class="gap-high">高</span></td>
  <td>仿真坐标系与真机存在系统性偏移，夹取点平均偏差约 15mm（现场问题 #1）</td>
  <td>开发半自动标定工具；仿真中增加位姿噪声建模 <br><strong>⭕ 待完成</strong></td>
</tr>
<tr>
  <td>摩擦 / 抓取力</td>
  <td><span class="gap-high">高</span></td>
  <td>MuJoCo 摩擦系数与真实金属器械差异大，仿真抓取成功但真机夹取器械易滑落</td>
  <td>采集真实夹持力数据，反校仿真摩擦参数 <br><strong>⭕ 待启动</strong></td>
</tr>
<tr>
  <td>图像域差异</td>
  <td><span class="gap-mid">中</span></td>
  <td>仿真渲染 vs 真实相机图像存在纹理、光照差异，影响 YOLO 检测置信度</td>
  <td>Isaac Sim 开启光线追踪；训练集混入真实图像做域随机化 <br><strong>🔄 进行中</strong></td>
</tr>
<tr>
  <td>Z 轴高度一致性</td>
  <td><span class="gap-mid">中</span></td>
  <td>真实托盘桌面不平整，不同位置 Z 偏移量不一致，导致夹取失败（问题 #3）</td>
  <td>仿真中加入桌面扰动建模；执行层增加高度自适应补偿 <br><strong>⭕ 设计中</strong></td>
</tr>
<tr>
  <td>语音 ASR 延迟</td>
  <td><span class="gap-low">低</span></td>
  <td>仿真中语音指令直接注入文本跳过 ASR；真机约 5s 延迟，手术室不可接受（问题 #9）</td>
  <td>接入流式 ASR（Whisper streaming / NeMo）<br><strong>🔄 进行中</strong></td>
</tr>
<tr>
  <td>器械台布局灵活性</td>
  <td><span class="gap-low">低</span></td>
  <td>仿真中托盘位置固定；真实手术室护士需按手术类型调整布局（问题 #5）</td>
  <td>规划多托盘自动识别方案；引入二维码辅助定位 <br><strong>⭕ 规划中</strong></td>
</tr>
</tbody>
</table>

</div>

---

## 第二级通过指标（Isaac Sim 门槛）

<div class="metrics-grid">
  <div class="metric-card">
    <div class="metric-val">≥97<span class="metric-unit">%</span></div>
    <div class="metric-lbl">抓取成功率</div>
    <div class="metric-now">当前：测试中</div>
  </div>
  <div class="metric-card">
    <div class="metric-val">≥98<span class="metric-unit">%</span></div>
    <div class="metric-lbl">递交成功率</div>
    <div class="metric-now">当前：测试中</div>
  </div>
  <div class="metric-card">
    <div class="metric-val">≤2.5<span class="metric-unit">s</span></div>
    <div class="metric-lbl">平均递交时延</div>
    <div class="metric-now">当前：未测</div>
  </div>
  <div class="metric-card">
    <div class="metric-val">≤80<span class="metric-unit">ms</span></div>
    <div class="metric-lbl">急停响应</div>
    <div class="metric-now">硬性约束</div>
  </div>
  <div class="metric-card">
    <div class="metric-val">0</div>
    <div class="metric-lbl">碰撞 /<br>误释放率</div>
    <div class="metric-now">硬性约束</div>
  </div>
</div>

五项指标全部达标 → 进入第三级真实机械臂测试。

---

<div class="doc-footer">
  <span>负责人：谭文韬（仿真）/ 任松（决策-感知链路）</span>
  <span>最近更新 2026-03-18</span>
</div>

# NLP 模块

<span class="status-wip">进行中</span> &emsp; **负责人：** 陈端端

---

## 模块目标

从语音指令或文本中准确识别医疗器械名称，输出标准化结果，支撑器械递交流程触发。

**对外承诺：** 输出符合 [`InstrumentCommand`](../../design/module_interfaces.md#instrumentcommand) 接口规范，识别置信度 ≥ 0.85。

---

## 上下游接口

=== "输入"

    | 来源 | 数据 | 说明 |
    |------|------|------|
    | 麦克风 / ASR | 原始文本字符串 | 语音转写结果 |
    | 手动输入 | 文本字符串 | GUI 输入，用于调试 |

=== "输出"

    | 消费方 | 数据 | 说明 |
    |--------|------|------|
    | 决策模块 | `InstrumentCommand` | 标准化器械名 + 置信度 |

完整字段定义见 [模块接口定义](../../design/module_interfaces.md#instrumentcommand)。

---

## 当前状态

| 子功能 | 状态 | 说明 |
|--------|------|------|
| Qwen2.5-0.5B SFT 微调 | <span class="status-wip">进行中</span> | 约 500 条数据，LoRA 微调中 |
| DPO 对齐优化 | <span class="status-todo">待完成</span> | SFT 完成后启动 |
| 器械标准化词库 | <span class="status-wip">进行中</span> | 覆盖 Top-30 器械，JSON 格式 |
| ASR 接入（流式） | <span class="status-wip">进行中</span> | Whisper streaming 方案调研中 |
| vLLM 部署推理 | <span class="status-todo">待完成</span> | 等 SFT 完成后部署 |

---

## 待决策问题

!!! question "D-03：ASR 方案选型"
    本地部署 Whisper streaming（低延迟，需 GPU）vs 云端 ASR（低配置要求，网络依赖）。  
    手术室无线网络稳定性存疑，倾向本地方案但需确认计算资源是否充足。  
    **目标：语音指令 → 识别结果 ≤ 1s。**

---

## 已知瓶颈

!!! failure "P1-03：ASR 延迟约 5 秒"
    当前语音识别延迟约 5 秒（现场测试问题 #9），手术场景中无法接受。  
    **改进方向：** 引入流式 ASR，边听边识别，目标 ≤ 1s 响应。

---

## 本周行动

- [ ] 陈端端：完成 SFT 训练第一轮，在验证集上跑通推理
- [ ] 陈端端：测试 Whisper streaming 本地部署延迟，输出对比数据
- [ ] 陈端端：词库补充到 50 条，覆盖神经外科常用器械

---

## 技术子页

- [Qwen2.5 SFT 微调](qwen_sft.md) — 数据集构建、训练配置、评测结果
- [DPO 对齐优化](dpo_alignment.md) — 偏好数据构建、训练策略
- [器械标准化词库](instrument_vocab.md) — 词库结构、维护规范

<div class="doc-footer">
  <span>负责人：陈端端</span>
  <span>最近更新 2026-03-18</span>
</div>

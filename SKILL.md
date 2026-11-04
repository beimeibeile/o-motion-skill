---
name: o-motion-skill
description: "用模板生成视频。给一个模板（.motion 文件或网页模板目录）、填好内容、指定输出文件名，即可产出成片 mp4：自动匹配渲染方式、自动检查成品，检查不通过不交付并说明原因。适合把现成模板批量做成短视频的普通用户，无需懂渲染。"
version: 0.3.0
author: O_Motion Project
license: MIT
repository: https://github.com/beimeibeile/o-motion-skill
capabilities:
  - name: template_to_video
    description: "模板生视频：输入模板 + 内容参数/素材，输出成片 mp4；自动选择渲染方式并在出片后校验成品"
    entry_point: render.py
    params:
      template: "str - 模板路径（.motion 文件，或网页模板目录）"
      output: "str - 成片 mp4 路径（已存在则拒绝执行，不覆盖旧文件）"
      params: "dict, optional - 模板块内容（JSON），字段名以模板说明为准"
      params_file: "str, optional - 内容 JSON 文件路径（推荐，避免终端吞引号）"
      width: "int, optional - .motion 一般不用填；网页模板为画面宽度，默认 1920"
      height: "int, optional - .motion 一般不用填；网页模板为画面高度，默认 1080"
      fps: "int, optional - .motion 一般不用填；网页模板为帧率，默认 60"
      end: "float, optional - 网页模板的全片时长（秒），网页模板必填"
      audio: "str, optional - 网页模板的配音/背景音 wav"
      playwright_module: "str, optional - 一般不用填，工具会自动查找模板自带模块"
      probe: "bool, optional - 只检查环境，不出片"
      core_dir: "str, optional - 渲染引擎位置（自动找不到时才需要）"
    fallback: null
---

# 用模板生成视频

给模板、填内容、指定输出文件名，拿到成片。

## 何时用

- 手上有现成模板（`.motion` 文件，或带 `_render` 的网页模板目录），想快速做成视频
- 要把同一个模板批量套不同文案，批量出片
- 不想研究渲染参数，只关心「内容对不对、片子能不能看」

不适合：从零设计新模板（那属于模板创作），或需要精细剪辑、转场、多轨混音的重型成片。

## 怎么用

**`.motion` 模板**：

```bash
python render.py --template 模板.motion --params-file 内容.json --output 成片.mp4
```

内容文件就是普通 JSON，字段名以模板作者的说明为准：

```json
{"title": "开场标题", "subtitle": "副标题", "body": "正文内容"}
```

**网页模板目录**：

```bash
python render.py --template ./模板目录 --end 12 --width 1080 --height 1920 \
    --fps 60 --audio 配音.wav --output 成片.mp4
```

- `--end`：全片时长（秒），网页模板必填，具体数值见模板目录的 README
- 竖屏写 1080×1920，横屏写 1920×1080
- 模板自带渲染模块会自动找到，通常不用手填

先用 `--probe` 确认环境就绪，再正式出片：

```bash
python render.py --template ./模板目录 --end 1 --probe --output unused.mp4
```

## 会自动做什么

1. **选渲染方式**：`.motion` 用引擎整链渲染；网页模板用模板自带渲染器
2. **渲染前查环境**：缺 Node.js / Chrome / FFmpeg 时提前拦下，不让你等到渲染一半才失败
3. **渲染后查成品**：能否正常播放、分辨率对不对、时长对不对、该有的音轨在不在
4. **不通过的就不交付**：明确列出哪项没过、怎么改；通过的才给文件

成品检查没有「跳过」开关。带提醒项（例如画面尾部静止、模板缺一份可选元数据）仍会出片，并在结果里逐条标出。

## 返回什么

默认给人看的摘要：成片路径、文件大小、检查结论、提醒项。
加 `--json` 返回完整结构化结果，便于接入其他程序。

## 已知限制

- `.motion` 的画面尺寸与帧率由模板决定，不能改；要别的画幅请换对应模板
- 网页模板目录必须自带 `_render/render_project.mjs`
- 参数名与模板绑定，填错字段名不报错、只呈现为空——务必照模板说明的字段名填
- 同一模板重复出片请换输出名，工具不覆盖已有文件（这是刻意设计）

## 出错时

报错末尾固定带一行「怎么办」，按它给出的动作处理即可。常见情形：

| 提示 | 怎么办 |
|---|---|
| 找不到渲染引擎 | 设 `MOTION_CORE_DIR`，或用 `--core-dir` 指定 |
| 缺少渲染所需组件 | 按提示装 Node.js / Chrome / FFmpeg |
| 输出文件已存在 | 换输出文件名 |
| 成品没通过检查 | 按列出的原因调内容或换模板 |

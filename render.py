#!/usr/bin/env python3
"""o-motion-skill：用模板生成视频

你只需要三样东西：一个模板、要填的内容、一个输出文件名。
渲染、环境检查、成品校验都由本工具自动完成。

用法（.motion 模板）：
    python render.py --template 模板.motion --params-file 内容.json --output 成片.mp4

用法（目录型网页模板）：
    python render.py --template ./模板目录 --end 12 --output 成片.mp4

遇到报错先看最后一行的「怎么办」提示，它一定给出了下一步动作。
"""

import argparse
import json
import os
import subprocess
import sys


class UserFacingError(Exception):
    """面向用户的错误：一句话说明 + 一句话怎么办。"""

    def __init__(self, message, action=None, detail=None):
        super().__init__(message)
        self.message = message
        self.action = action
        self.detail = detail


def find_motion_core(explicit=None):
    """定位渲染引擎（Motion-Core）。

    查找顺序：--core-dir > MOTION_CORE_DIR > 本工具同级/上两级目录。
    以 core/invoke.py 是否存在为准，避免认到一个空目录。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if explicit:
        cand = os.path.abspath(os.path.normpath(explicit))
        if os.path.isfile(os.path.join(cand, "core", "invoke.py")):
            return cand
        raise UserFacingError(
            f"指定的引擎目录不可用：{explicit}",
            action="确认该目录下确实有 core/invoke.py，或去掉 --core-dir 让工具自动查找。",
        )
    candidates = []
    env = os.environ.get("MOTION_CORE_DIR")
    if env:
        candidates.append(env)
    candidates.extend([
        os.path.join(here, "Motion-Core"),
        os.path.join(here, "..", "Motion-Core"),
        os.path.join(here, "..", "..", "Motion-Core"),
    ])
    for cand in candidates:
        cand = os.path.abspath(os.path.normpath(cand))
        if os.path.isfile(os.path.join(cand, "core", "invoke.py")):
            return cand
    return None


def _load_invoke(core_dir):
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    from core.invoke import invoke
    return invoke


def _require_output_free(output):
    """输出文件已存在时拒绝执行，避免覆盖用户已有文件。"""
    if os.path.exists(output):
        raise UserFacingError(
            f"输出文件已存在：{output}",
            action="换一个输出文件名（例如加 _v2），本工具不会覆盖已有文件。",
        )


def _quality_failures(report):
    """从质量报告里取出失败项，转成人能看懂的原因。"""
    return [f"{c.get('name', '检查项')}：{c.get('message', '未通过')}"
            for c in report.get("checks", []) if c.get("status") == "fail"]


def load_params(params_text, params_file):
    """读取模板参数：优先文件，其次命令行 JSON。"""
    if params_file:
        path = os.path.abspath(params_file)
        if not os.path.isfile(path):
            raise UserFacingError(
                f"参数文件不存在：{params_file}",
                action="检查文件路径是否正确。",
            )
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise UserFacingError(
                f"参数文件不是合法 JSON：{params_file}",
                action="用 JSON 校验工具检查一遍，常见问题是多了一个逗号或少了引号。",
                detail=str(e),
            )
        if not isinstance(data, dict):
            raise UserFacingError(
                "参数文件内容必须是 JSON 对象（形如 {\"标题\": \"内容\"}）",
                action="把最外层改成大括号包裹的对象。",
            )
        return data

    if not params_text:
        return {}

    try:
        data = json.loads(params_text)
    except json.JSONDecodeError as e:
        raise UserFacingError(
            "命令行参数不是合法 JSON",
            action="建议改用 --params-file 指定一个 JSON 文件；"
                   "直接把 JSON 写在命令行里容易被终端吞掉引号。",
            detail=str(e),
        )
    if not isinstance(data, dict):
        raise UserFacingError(
            "参数必须是 JSON 对象（形如 {\"标题\": \"内容\"}）",
            action="把最外层改成大括号包裹的对象。",
        )
    return data


def detect_playwright_module(template_dir):
    """自动寻找目录模板自带的 playwright-core，省得用户手填路径。"""
    for rel in ("node_modules/playwright-core",
                "_render/node_modules/playwright-core",
                "../node_modules/playwright-core"):
        cand = os.path.abspath(os.path.join(template_dir, rel))
        if os.path.isdir(cand):
            return cand
    return None


def render_motion(core_dir, template, params, output, width, height, fps):
    """模板是 .motion 文件：交给渲染引擎跑完整链路。"""
    invoke = _load_invoke(core_dir)

    parsed = invoke("motion_template_parse", template_path=template)
    if not parsed.get("success"):
        raise UserFacingError(
            "模板读取失败",
            action="确认这是一个完整的 .motion 模板文件（不是压缩包的一部分，也没有被改名）。",
            detail=str(parsed.get("error")),
        )
    parsed_info = parsed.get("result") or {}
    if not parsed_info.get("runtime_entry"):
        raise UserFacingError(
            "这个模板缺少可渲染的入口，无法出片",
            action="换一个模板试试；如果这个模板是刚下载的，可能文件不完整，建议重新下载。",
        )

    # 画面尺寸和帧率以模板自身声明为准；只在用户显式给出时做一致性校验
    render_kwargs = {"template_path": template, "params": params, "output_path": output}
    if width is not None:
        render_kwargs["width"] = width
    if height is not None:
        render_kwargs["height"] = height
    if fps is not None:
        render_kwargs["fps"] = fps

    r = invoke("motion_template_render", **render_kwargs)
    if not r.get("success"):
        raise UserFacingError(
            "渲染失败",
            action="看下面的原因：参数与模板不匹配就改参数；"
                   "提示缺少依赖就按提示装好再重试。",
            detail=str(r.get("error")),
        )

    q = invoke("motion_quality_check", template_path=template,
               params=params, output_path=output)
    if not q.get("success"):
        raise UserFacingError(
            "成品检查执行失败",
            action="渲染已完成但没能校验成品，请把这条错误反馈给维护者。",
            detail=str(q.get("error")),
        )
    report = q.get("result") or {}
    if report.get("status") == "fail":
        raise UserFacingError(
            "成品没通过检查，已停止交付",
            action="下面的原因里如果能改（比如文字超长），改参数后重跑；"
                   "如果是模板自身问题，换一个模板。",
            detail="\n".join(_quality_failures(report)),
        )

    return {"render": r.get("result"), "quality": report}


def render_dir_template(template_dir, args, core_dir):
    """模板是一个网页模板目录：先自检环境，再用模板自带渲染器出片。"""
    renderer = os.path.join(template_dir, "_render", "render_project.mjs")
    if not os.path.isfile(renderer):
        raise UserFacingError(
            "这个目录不是可直接渲染的模板",
            action="确认目录里应该有 _render/render_project.mjs；"
                   "如果是 .motion 文件，请直接指向那个文件而不是目录。",
        )

    invoke = _load_invoke(core_dir)
    doctor = invoke("motion_doctor", template_dir=template_dir)
    if not doctor.get("success"):
        raise UserFacingError(
            "环境检查没能执行",
            action="请把这条错误反馈给维护者。",
            detail=str(doctor.get("error")),
        )
    doc = doctor.get("result") or {}
    if not doc.get("healthy"):
        missing = [f"{i['name']}（{i.get('detail', '')}）"
                   for i in doc.get("environment", []) if i.get("status") == "missing"]
        raise UserFacingError(
            "这台电脑缺少渲染所需的组件：",
            action="按上面列出的名称逐个安装后重试（Node.js、Chrome、FFmpeg 都是常规软件）。",
            detail="；".join(missing),
        )

    width = args.width or 1920
    height = args.height or 1080
    fps = args.fps or 60

    playwright_module = args.playwright_module or detect_playwright_module(template_dir)

    cmd = [
        "node", renderer, "index.html",
        "--start", "0",
        "--end", str(args.end),
        "--fps", str(fps),
        "--width", str(width),
        "--height", str(height),
    ]
    # 模板渲染器的约束：--output / --stills-dir / --probe 三选一
    if args.probe:
        cmd += ["--probe"]
    else:
        cmd += ["--output", args.output]
    if args.audio:
        cmd += ["--audio", args.audio]
    if playwright_module:
        cmd += ["--playwright-module", playwright_module]
    if args.verbose:
        print("执行的命令：" + " ".join(cmd), flush=True)

    proc = subprocess.run(cmd, cwd=template_dir)
    if proc.returncode != 0:
        raise UserFacingError(
            f"模板渲染器返回失败（退出码 {proc.returncode}）",
            action="先看模板目录里的 README 确认用法；"
                   "如果是缺少模块，在模板目录执行 npm install 后重试。",
        )

    if args.probe:
        return {"doctor": doc, "render": {"probe": True, "output": None},
                "quality": None}

    # 成品检查：任何来源的视频都能查，不依赖模板类型
    from core.quality_gate import CheckStatus, QualityGate, QualityReport
    gate = QualityGate()
    report = QualityReport(template=template_dir)
    report.checks = gate.check_output(
        args.output,
        {"width": width, "height": height,
         "duration": args.end, "require_audio": bool(args.audio)},
    )
    failed = [c for c in report.checks if c.status == CheckStatus.FAIL]
    warned = [c for c in report.checks if c.status == CheckStatus.WARN]
    if failed:
        report.status = CheckStatus.FAIL
    elif warned:
        report.status = CheckStatus.WARN
    else:
        report.status = CheckStatus.PASS
    qdict = report.to_dict()
    if qdict["status"] == "fail":
        raise UserFacingError(
            "成品没通过检查，已停止交付",
            action="看下面的原因调整后重跑。",
            detail="\n".join(_quality_failures(qdict)),
        )

    return {"doctor": doc, "render": {"output": args.output}, "quality": qdict}


def print_summary(output, result):
    """人读的成功摘要：只说用户关心的事。"""
    quality = result.get("quality") or {}
    status = quality.get("status")
    print("")
    print(f"出片成功：{os.path.abspath(output)}")
    try:
        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"文件大小：{size_mb:.1f} MB")
    except OSError:
        pass
    if status:
        print(f"成品检查：{'通过' if status == 'pass' else '通过（有提醒项）'}")
        for c in quality.get("checks", []):
            if c.get("status") == "warn":
                print(f"  提醒：{c.get('name', '')} - {c.get('message', '')}")


def build_parser():
    ap = argparse.ArgumentParser(
        description="用模板生成视频：指定模板和内容，自动出片并自检",
        epilog="提示：命令行里写 JSON 容易被终端吞引号，内容较多时请用 --params-file。",
    )
    ap.add_argument("--template", required=True,
                    help="模板：.motion 文件，或目录型网页模板的目录")
    ap.add_argument("--output", required=True,
                    help="输出的 mp4 路径（文件已存在时会拒绝执行，避免覆盖）")
    ap.add_argument("--params", default=None,
                    help=".motion 模板的填参 JSON（少量参数可直接写在命令行）")
    ap.add_argument("--params-file", default=None,
                    help=".motion 模板的填参 JSON 文件（推荐，避免引号问题）")
    ap.add_argument("--width", type=int, default=None,
                    help=".motion：一般不用填，模板自己决定；目录模板：画面宽度，默认 1920")
    ap.add_argument("--height", type=int, default=None,
                    help=".motion：一般不用填，模板自己决定；目录模板：画面高度，默认 1080")
    ap.add_argument("--fps", type=int, default=None,
                    help=".motion：一般不用填，模板自己决定；目录模板：帧率，默认 60")
    ap.add_argument("--end", type=float, default=None,
                    help="目录模板：全片时长（秒），目录模板必填，见模板 README")
    ap.add_argument("--audio", default=None,
                    help="目录模板：配音或背景音的 wav 文件路径")
    ap.add_argument("--playwright-module", default=None,
                    help="目录模板：一般不用填，工具会自动找模板自带的模块")
    ap.add_argument("--probe", action="store_true",
                    help="只做预检，不生成视频（用于确认环境是否就绪）")
    ap.add_argument("--core-dir", default=None,
                    help="渲染引擎目录（一般不用填，工具会自动查找）")
    ap.add_argument("--json", action="store_true",
                    help="输出完整 JSON 结果（给程序读取用）")
    ap.add_argument("--verbose", action="store_true",
                    help="显示执行的底层命令与详细报错")
    return ap


def main():
    args = build_parser().parse_args()

    try:
        if not args.probe:
            _require_output_free(args.output)

        core_dir = find_motion_core(args.core_dir)
        if not core_dir:
            raise UserFacingError(
                "找不到渲染引擎（Motion-Core）",
                action="设置环境变量 MOTION_CORE_DIR 指向引擎目录，"
                       "或用 --core-dir 指定；引擎目录下应该能看到 core/invoke.py。",
            )

        if os.path.isdir(args.template):
            if not args.end:
                raise UserFacingError(
                    "目录型模板需要知道全片时长",
                    action="加 --end <秒数>，具体数值见模板目录里的 README。",
                )

        if os.path.isdir(args.template):
            result = render_dir_template(os.path.abspath(args.template), args, core_dir)
        else:
            if not os.path.isfile(args.template):
                raise UserFacingError(
                    f"模板不存在：{args.template}",
                    action="检查路径是否正确，注意文件名里的中文和空格。",
                )
            params = load_params(args.params, args.params_file)
            result = render_motion(core_dir, args.template, params, args.output,
                                   args.width, args.height, args.fps)

    except UserFacingError as e:
        print("")
        print(f"出问题了：{e.message}")
        if e.detail:
            print(f"原因：{e.detail}")
        if e.action:
            print(f"怎么办：{e.action}")
        sys.exit(1)

    if args.json:
        print(json.dumps({"success": True, "result": result},
                         ensure_ascii=False, indent=2))
    else:
        if result.get("quality") is not None or result.get("render", {}).get("probe"):
            print_summary(args.output, result)


if __name__ == "__main__":
    main()

"""小米运动健康命令行工具。

子命令：
    qr-login   扫码登录并保存 token
    relatives  列出亲友
    latest     查询最新数据快照
    history    查询按日历史数据
    summary    查询每日综合摘要
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from mi_fitness.auth import XiaomiAuth
from mi_fitness.client import MiHealthClient
from mi_fitness.exceptions import AuthError, MiSDKError
from mi_fitness.query import (
    DEFAULT_TOKEN_FILE,
    HISTORY_KEYS,
    get_history,
    get_latest,
    get_summary,
    list_relatives,
    resolve_relative_uid,
    resolve_token_path,
)

TOKEN_FILE = DEFAULT_TOKEN_FILE


def _print_qr_to_terminal(data: str) -> None:
    """用 Unicode 半块字符将二维码紧凑渲染到终端。"""
    try:
        import qrcode
        import qrcode.constants
    except ImportError as e:
        raise RuntimeError(
            "终端二维码渲染需要 qrcode，请安装：pip install 'mi-fitness[cli]'"
        ) from e

    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    # 补齐奇数行
    if len(matrix) % 2:
        matrix.append([False] * len(matrix[0]))

    # 每两行像素合并为一行字符：用 ▀▄█ 和空格表示四种组合
    # False = 白色模块（前景色块），True = 黑色模块（背景留空）
    for r in range(0, len(matrix), 2):
        line: list[str] = []
        for c in range(len(matrix[0])):
            top_white = not matrix[r][c]
            bot_white = not matrix[r + 1][c]
            if top_white and bot_white:
                line.append("\u2588")  # █
            elif top_white:
                line.append("\u2580")  # ▀
            elif bot_white:
                line.append("\u2584")  # ▄
            else:
                line.append(" ")
        print("".join(line))


# region 输出格式化
def _dump(payload: Any) -> None:
    """以 UTF-8 JSON 输出，便于脚本与 agent 消费。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _format_table(rows: list[dict[str, Any]]) -> str:
    """把同构字典列表渲染为简单文本表格。"""
    if not rows:
        return "(无数据)"
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    def cell(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    widths = [len(name) for name in columns]
    body = [[cell(row.get(name)) for name in columns] for row in rows]
    for values in body:
        for i, value in enumerate(values):
            widths[i] = max(widths[i], len(value))

    header = "  ".join(name.ljust(widths[i]) for i, name in enumerate(columns))
    separator = "  ".join("-" * width for width in widths)
    lines = [header, separator]
    lines.extend(
        "  ".join(value.ljust(widths[i]) for i, value in enumerate(values)) for values in body
    )
    return "\n".join(lines)


def _emit(payload: Any, output: str) -> None:
    """按 --format 输出结果。"""
    if output == "json":
        _dump(payload)
        return
    rows = payload if isinstance(payload, list) else [payload]
    print(_format_table([row for row in rows if isinstance(row, dict)]))
    if payload == []:
        print("(无数据)")


# endregion


# region 登录
async def _qr_login(token_path: Path | str | None = None) -> None:
    path = resolve_token_path(token_path) if token_path is not None else TOKEN_FILE

    async def show_qr(qr_image_url: str, login_url: str) -> None:
        print("\n📱 请用小米账号 APP 扫描二维码登录\n")
        if login_url:
            _print_qr_to_terminal(login_url)
        print(f"\n   二维码图片: {qr_image_url}")
        if login_url:
            print(f"   浏览器打开: {login_url}")
        print("\n⏳ 等待扫码...\n")

    async with XiaomiAuth() as auth:
        try:
            await auth.login_qr(qr_callback=show_qr)
        except AuthError as e:
            print(f"❌ 扫码登录失败: {e}")
            raise

        auth.save_token(path)
        print(f"✅ 扫码登录成功！user_id = {auth.token.user_id}")
        print(f"   Token 已保存至 {path.resolve()}")


# endregion


# region 数据查询
async def _run_query(args: argparse.Namespace) -> Any:
    """执行数据查询并返回可序列化结果。"""
    token_path = resolve_token_path(args.token)
    async with MiHealthClient.from_token(token_path) as client:
        if args.command == "relatives":
            return await list_relatives(client)

        relative_uid = args.uid
        if relative_uid is None:
            if not args.relative:
                raise SystemExit("请通过 --uid 或 --relative 指定亲友")
            relative_uid = resolve_relative_uid(await list_relatives(client), args.relative)

        if args.command == "latest":
            return await get_latest(client, relative_uid)

        if args.command == "history":
            return await get_history(
                client,
                relative_uid,
                args.key,
                query_date=args.date,
                days=args.days,
            )

        if args.command == "summary":
            return await get_summary(
                client,
                relative_uid,
                query_date=args.date,
                latest=args.latest,
            )

    raise SystemExit(f"未知命令: {args.command}")


# endregion


# region 参数解析
def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--token",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"token 路径（默认 {DEFAULT_TOKEN_FILE}，或环境变量 MI_FITNESS_TOKEN）",
    )
    parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        help="输出格式（默认 json）",
    )


def _add_relative_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--uid", type=int, default=None, help="亲友 UID")
    parser.add_argument("--relative", default=None, metavar="KEYWORD", help="按备注名匹配亲友")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD: {value}") from e


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mi-fitness",
        description="小米运动健康亲友数据命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command")

    login = subparsers.add_parser("qr-login", help="扫码登录并保存 token")
    login.add_argument(
        "--token",
        type=Path,
        default=TOKEN_FILE,
        metavar="PATH",
        help=f"token 保存路径（默认 {TOKEN_FILE}）",
    )

    relatives = subparsers.add_parser("relatives", help="列出亲友")
    _add_common_options(relatives)

    latest = subparsers.add_parser("latest", help="查询最新数据快照")
    _add_common_options(latest)
    _add_relative_options(latest)

    history = subparsers.add_parser("history", help="查询按日历史数据")
    _add_common_options(history)
    _add_relative_options(history)
    history.add_argument("--key", required=True, choices=HISTORY_KEYS, help="数据类型")
    history.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="窗口结束日（默认今天）",
    )
    history.add_argument(
        "--days",
        type=int,
        default=1,
        metavar="N",
        help="窗口天数，1..365（默认 1）",
    )

    summary = subparsers.add_parser("summary", help="查询每日综合摘要")
    _add_common_options(summary)
    _add_relative_options(summary)
    summary.add_argument(
        "--date",
        type=_parse_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="查询日期（默认今天）",
    )
    summary.add_argument(
        "--latest",
        action="store_true",
        help="使用最近一次同步日（与 --date 互斥，优先）",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI 入口。"""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "qr-login"):
        asyncio.run(_qr_login(getattr(args, "token", None)))
        return

    try:
        payload = asyncio.run(_run_query(args))
    except (MiSDKError, LookupError, ValueError) as e:
        raise SystemExit(f"❌ {e}") from e

    _emit(payload, args.format)


# endregion


if __name__ == "__main__":
    main()

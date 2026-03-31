import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import pyautogui


@dataclass
class Config:
    confidence: float
    pause_after_click: float
    stay_seconds: float
    scroll_step: int
    scroll_attempts_per_target: int
    retry_find_times: int
    retry_interval: float


def load_config(path: Path) -> Config:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(
        confidence=float(data.get("confidence", 0.84)),
        pause_after_click=float(data.get("pause_after_click", 0.4)),
        stay_seconds=float(data.get("stay_seconds", 5.0)),
        scroll_step=int(data.get("scroll_step", -650)),
        scroll_attempts_per_target=int(data.get("scroll_attempts_per_target", 8)),
        retry_find_times=int(data.get("retry_find_times", 5)),
        retry_interval=float(data.get("retry_interval", 0.5)),
    )


def rand_sleep(base: float, jitter: float = 0.25) -> None:
    time.sleep(max(0.05, base + random.uniform(-jitter, jitter)))


def locate_center(image_path: Path, confidence: float) -> Optional[Tuple[int, int]]:
    try:
        pos = pyautogui.locateCenterOnScreen(str(image_path), confidence=confidence)
    except Exception:
        pos = None
    if pos is None:
        return None
    return int(pos.x), int(pos.y)


def find_with_retry(image_path: Path, cfg: Config) -> Optional[Tuple[int, int]]:
    for _ in range(cfg.retry_find_times):
        pos = locate_center(image_path, cfg.confidence)
        if pos:
            return pos
        rand_sleep(cfg.retry_interval, 0.1)
    return None


def click_pos(pos: Tuple[int, int], cfg: Config) -> None:
    pyautogui.moveTo(pos[0], pos[1], duration=0.2)
    pyautogui.click()
    rand_sleep(cfg.pause_after_click)


def click_template(image_path: Path, cfg: Config, required: bool = True) -> bool:
    pos = find_with_retry(image_path, cfg)
    if not pos:
        if required:
            print(f"[ERR] 未找到模板: {image_path}")
        return False
    click_pos(pos, cfg)
    return True


def find_target_with_scroll(target_img: Path, cfg: Config) -> bool:
    for i in range(cfg.scroll_attempts_per_target):
        if click_template(target_img, cfg, required=False):
            print(f"[OK] 命中目标: {target_img.name} (scroll_try={i})")
            return True
        pyautogui.scroll(cfg.scroll_step)
        rand_sleep(0.45, 0.15)
    print(f"[ERR] 滚动后仍未找到: {target_img.name}")
    return False


def do_enter_and_back(templates: Path, cfg: Config) -> None:
    rand_sleep(cfg.stay_seconds, 0.3)

    back_img = templates / "back_arrow.png"
    if not click_template(back_img, cfg, required=True):
        raise RuntimeError("返回箭头未找到，无法继续")

    exit_img = templates / "exit_popup_exit.png"
    clicked = click_template(exit_img, cfg, required=False)
    if clicked:
        print("[OK] 已点击弹窗退出")
    else:
        print("[WARN] 未检测到退出弹窗，继续")
    rand_sleep(0.8, 0.2)


def run_for_year_flat(year: int, templates: Path, cfg: Config) -> None:
    year_img = templates / f"year_{year}.png"
    print(f"\n=== 年份 {year}（直接进入）===")
    ok = find_target_with_scroll(year_img, cfg)
    if not ok:
        return
    do_enter_and_back(templates, cfg)


def run_for_year_with_types(year: int, templates: Path, cfg: Config) -> None:
    year_img = templates / f"year_{year}.png"
    type_imgs = [
        templates / "type_single.png",
        templates / "type_multi.png",
        templates / "type_analysis.png",
    ]
    print(f"\n=== 年份 {year}（展开三类题）===")
    ok = find_target_with_scroll(year_img, cfg)
    if not ok:
        return

    for img in type_imgs:
        if not click_template(img, cfg, required=False):
            print(f"[WARN] 未找到题型模板: {img.name}")
            continue
        print(f"[OK] 进入题型: {img.name}")
        do_enter_and_back(templates, cfg)
        click_template(year_img, cfg, required=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="微信小程序刷题页自动点击采集辅助")
    parser.add_argument("--templates", default="templates", help="模板图片目录")
    parser.add_argument("--config", default="ui_capture_config.json", help="配置文件路径")
    parser.add_argument(
        "--years",
        default="2025,2024,2023,2022,2021,2020,2019,2018,2017,2016,2015,2014,2013",
        help="年份列表，逗号分隔",
    )
    parser.add_argument("--countdown", type=int, default=5, help="启动前倒计时秒")
    args = parser.parse_args()

    templates = Path(args.templates)
    cfg = load_config(Path(args.config))
    years = [int(x.strip()) for x in args.years.split(",") if x.strip()]

    missing = [
        p for p in [
            templates / "back_arrow.png",
            templates / "exit_popup_exit.png",
            templates / "type_single.png",
            templates / "type_multi.png",
            templates / "type_analysis.png",
        ] if not p.exists()
    ]
    if missing:
        print("缺少模板文件：")
        for p in missing:
            print(" -", p)
        print("请先补齐模板图片。")
        return 2

    pyautogui.FAILSAFE = True
    print("请将微信小程序窗口切到前台，并停在题库列表页顶部。")
    for i in range(args.countdown, 0, -1):
        print(f"{i}...")
        time.sleep(1)

    for y in years:
        year_img = templates / f"year_{y}.png"
        if not year_img.exists():
            print(f"[WARN] 缺少年份模板，跳过 {y}: {year_img.name}")
            continue

        # 2024/2025 需要展开题型，其他年份按你描述是直接进入刷题页。
        if y in (2025, 2024):
            run_for_year_with_types(y, templates, cfg)
        else:
            run_for_year_flat(y, templates, cfg)

    print("\n全部流程结束。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

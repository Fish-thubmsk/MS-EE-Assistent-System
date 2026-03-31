import argparse
import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE = "https://api.wisapp.cn/jingyantiku/api"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781 MiniProgramEnv/Windows"
)


def clean_text(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [clean_text(x) for x in value]
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_answer(answer: Any) -> Any:
    if answer is None:
        return None
    if isinstance(answer, list):
        if not answer:
            return []
        if all(isinstance(x, int) or (isinstance(x, str) and x.isdigit()) for x in answer):
            return "".join(chr(ord("A") + int(x)) for x in answer)
        return [clean_text(x) for x in answer]
    if isinstance(answer, str):
        return clean_text(answer)
    return answer


def get_json(url: str, timeout: int = 30) -> Dict[str, Any]:
    req = Request(
        url,
        headers={
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "user-agent": UA,
            "x-platform": "mp",
            "x-systemtype": "windows",
            "xweb_xhr": "1",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def build_url(path: str, params: Dict[str, Any]) -> str:
    return f"{BASE}/{path}?{urlencode(params)}"


def fetch_chapters(qbank_id: int, token: str) -> List[Dict[str, Any]]:
    url = build_url(
        "chapter",
        {"qBankId": qbank_id, "rewardedAd": 1, "app": "true", "token": token},
    )
    obj = get_json(url)
    if obj.get("errno") != 0:
        raise RuntimeError(f"chapter 接口失败: errno={obj.get('errno')} errmsg={obj.get('errmsg')}")
    rows: List[Dict[str, Any]] = []
    for year_node in obj.get("data", []):
        year_match = re.search(r"\d{4}", str(year_node.get("title", "")))
        year = int(year_match.group(0)) if year_match else None
        for ch in year_node.get("children", []) or []:
            rows.append(
                {
                    "year": year,
                    "yearTitle": year_node.get("title"),
                    "chapterId": ch.get("id"),
                    "chapterTitle": ch.get("title"),
                    "expectedQuestionCount": ch.get("questionCount"),
                }
            )
    return rows


def map_question(q: Dict[str, Any]) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": q.get("id"),
        "type": str(q.get("type")) if q.get("type") is not None else None,
        "stem": clean_text(q.get("stem")),
        "options": [clean_text(x) for x in q.get("options", [])],
        "answer": normalize_answer(q.get("answer")),
        "analysis": clean_text(q.get("analysis")),
        "source": clean_text(q.get("source")),
        "difficulty": q.get("difficulty"),
        "score": q.get("score"),
    }
    if q.get("subQuestion"):
        item["subQuestions"] = [
            {
                "id": sq.get("id"),
                "type": str(sq.get("type")) if sq.get("type") is not None else None,
                "stem": clean_text(sq.get("stem")),
                "options": [clean_text(x) for x in sq.get("options", [])],
                "answer": normalize_answer(sq.get("answer")),
                "analysis": clean_text(sq.get("analysis")),
                "score": sq.get("score"),
            }
            for sq in q.get("subQuestion", [])
        ]
    return item


def fetch_questions(qbank_id: int, chapter_id: int, token: str) -> Dict[str, Any]:
    url = build_url(
        "v1/question/sequence_practise_nestification",
        {
            "app": "true",
            "token": token,
            "qBankId": qbank_id,
            "chapterId": chapter_id,
            "studentAnswer": 1,
        },
    )
    obj = get_json(url)
    if obj.get("errno") != 0:
        raise RuntimeError(
            f"questions 接口失败: chapterId={chapter_id} errno={obj.get('errno')} errmsg={obj.get('errmsg')}"
        )
    data = obj.get("data") or {}
    questions = [map_question(q) for q in data.get("questions", [])]
    return {"title": data.get("title"), "questions": questions}


def main() -> int:
    parser = argparse.ArgumentParser(description="批量抓取题库并输出结构化精简 JSON")
    parser.add_argument("--token", required=True, help="从抓包中复制的最新 token")
    parser.add_argument("--qbank-id", type=int, default=5, help="题库 ID，默认 5")
    parser.add_argument(
        "--output",
        default="题库_结构化精简_自动抓取.json",
        help="输出 JSON 文件路径",
    )
    parser.add_argument("--sleep-ms", type=int, default=200, help="每个章节请求间隔毫秒")
    args = parser.parse_args()

    chapters = fetch_chapters(args.qbank_id, args.token)
    result_chapters: List[Dict[str, Any]] = []

    for i, ch in enumerate(chapters, start=1):
        chapter_id = int(ch["chapterId"])
        data = fetch_questions(args.qbank_id, chapter_id, args.token)
        result_chapters.append(
            {
                "year": ch["year"],
                "yearTitle": ch["yearTitle"],
                "chapterId": chapter_id,
                "chapterTitle": ch["chapterTitle"],
                "expectedQuestionCount": ch["expectedQuestionCount"],
                "questionCount": len(data["questions"]),
                "questions": data["questions"],
            }
        )
        print(f"[{i}/{len(chapters)}] chapterId={chapter_id} {ch['chapterTitle']} -> {len(data['questions'])} 题")
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000.0)

    out_obj = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "qBankId": args.qbank_id,
        "totalChapters": len(result_chapters),
        "totalQuestions": sum(x["questionCount"] for x in result_chapters),
        "chapters": result_chapters,
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        raise SystemExit(130)

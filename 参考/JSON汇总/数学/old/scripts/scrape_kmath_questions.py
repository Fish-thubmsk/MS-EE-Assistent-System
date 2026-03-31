import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen


BASE_URL = "https://kmath.cn/math/"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def fetch_html(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": DEFAULT_UA})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def html_to_text(fragment: str) -> str:
    x = re.sub(r"<!--[\s\S]*?-->", " ", fragment)
    x = re.sub(r"<script[\s\S]*?</script>", " ", x, flags=re.I)
    x = re.sub(r"<style[\s\S]*?</style>", " ", x, flags=re.I)
    x = re.sub(r"<br\s*/?>", "\n", x, flags=re.I)
    x = re.sub(r"</p\s*>", "\n", x, flags=re.I)
    x = re.sub(r"<[^>]+>", " ", x)
    x = unescape(x)
    x = re.sub(r"[ \t\r\f\v]+", " ", x)
    x = re.sub(r"\n\s*\n+", "\n", x)
    return x.strip()


def extract_paper_ids(collection_html: str) -> List[str]:
    ids = re.findall(r"papername\.aspx\?paperid=(\d+)", collection_html, flags=re.I)
    return dedupe_keep_order(ids)


def extract_max_page(collection_html: str, collection_id: str) -> int:
    links = re.findall(
        rf"collection\.aspx\?id={re.escape(collection_id)}(?:&amp;|&)Page=(\d+)",
        collection_html,
        flags=re.I,
    )
    pages = [int(x) for x in links]
    return max(pages) if pages else 1


def extract_detail_ids(paper_html: str) -> List[str]:
    ids = re.findall(r"detail\.aspx\?id=(\d+)", paper_html, flags=re.I)
    return dedupe_keep_order(ids)


def extract_paper_title(paper_html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", paper_html, flags=re.I | re.S)
    if not m:
        return ""
    title = html_to_text(m.group(1))
    return title.split("-数学试卷")[0].strip()


def extract_paper_detail_html(paper_html: str) -> str:
    m = re.search(
        r'<div\s+class="paper_detail"[^>]*>([\s\S]*?)<div\s+class="paper_right"',
        paper_html,
        flags=re.I,
    )
    if m:
        return m.group(1)
    return paper_html


def normalize_question_type(cat_text: str) -> str:
    t = html_to_text(cat_text)
    if "单选" in t:
        return "single_choice"
    if "填空" in t:
        return "fill_blank"
    if "解答" in t or "大题" in t:
        return "subjective"
    return "unknown"


def parse_option_text(raw_html: str) -> Optional[Tuple[str, str]]:
    text = html_to_text(raw_html)
    if not text:
        return None

    m = re.search(r"\\text\{([A-F])\.\}", raw_html, flags=re.I)
    if m:
        letter = m.group(1).upper()
        body = re.sub(r"^\$?\\text\{[A-F]\.\}\$?\s*", "", text).strip()
        return (letter, body) if body else None

    m2 = re.match(r"^\s*([A-F])[\.、]\s*(.+)$", text, flags=re.I)
    if m2:
        return m2.group(1).upper(), m2.group(2).strip()

    return None


def parse_questions_from_paper(paper_html: str, paper_id: str) -> List[Dict]:
    detail = extract_paper_detail_html(paper_html)
    cat_matches = list(
        re.finditer(
            r'<div[^>]*class="cat"[^>]*>\s*<span[^>]*>([\s\S]*?)</span>\s*</div>',
            detail,
            flags=re.I,
        )
    )
    view_matches = list(
        re.finditer(
            r'<div[^>]*(?:class="view_ques"[^>]*data-tid\s*=\s*"?(\d+)"?|'
            r'data-tid\s*=\s*"?(\d+)"?[^>]*class="view_ques")[^>]*>([\s\S]*?)</div>\s*'
            r'<div[^>]*class="layui-card-foot"',
            detail,
            flags=re.I,
        )
    )

    questions: List[Dict] = []
    cat_idx = 0
    current_cat_text = ""
    current_cat_type = "unknown"

    for qm in view_matches:
        while cat_idx < len(cat_matches) and cat_matches[cat_idx].start() < qm.start():
            current_cat_text = html_to_text(cat_matches[cat_idx].group(1))
            current_cat_type = normalize_question_type(current_cat_text)
            cat_idx += 1

        qid = qm.group(1) or qm.group(2)
        qhtml = qm.group(3)
        stem_m = re.search(r'<div[^>]*class="ques"[^>]*>([\s\S]*?)</div>', qhtml, flags=re.I)
        stem = html_to_text(stem_m.group(1)) if stem_m else ""
        if not stem:
            continue

        options: Dict[str, str] = {}
        for om in re.finditer(r'<span[^>]*class="opt"[^>]*>([\s\S]*?)</span>', qhtml, flags=re.I):
            parsed = parse_option_text(om.group(1))
            if parsed:
                letter, body = parsed
                options[letter] = body

        questions.append(
            {
                "question_id": qid,
                "question_url": f"{BASE_URL}detail.aspx?id={qid}",
                "question_type": current_cat_type,
                "question_type_text": current_cat_text,
                "stem": stem,
                "options": options,
            }
        )

    return questions


def fetch_paper_ids_by_pages(collection_id: str, max_pages: int) -> Tuple[List[str], int]:
    all_ids: List[str] = []
    reached_pages = 0

    first_url = f"{BASE_URL}collection.aspx?id={collection_id}"
    print(f"[INFO] Fetch collection page 1: {first_url}")
    first_html = fetch_html(first_url)
    reached_pages = 1
    all_ids.extend(extract_paper_ids(first_html))

    detected_max = extract_max_page(first_html, collection_id)
    if max_pages > 0:
        detected_max = min(detected_max, max_pages)

    for page in range(2, detected_max + 1):
        page_url = f"{BASE_URL}collection.aspx?id={collection_id}&Page={page}"
        print(f"[INFO] Fetch collection page {page}: {page_url}")
        html = fetch_html(page_url)
        reached_pages = page
        page_ids = extract_paper_ids(html)
        if not page_ids:
            break
        all_ids.extend(page_ids)

    return dedupe_keep_order(all_ids), reached_pages


def fetch_and_parse_paper(paper_id: str, max_questions_per_paper: int) -> Dict:
    paper_url = f"{BASE_URL}papername.aspx?paperid={paper_id}"
    paper_html = fetch_html(paper_url)
    paper_title = extract_paper_title(paper_html)
    questions = parse_questions_from_paper(paper_html, paper_id)
    if max_questions_per_paper > 0:
        questions = questions[:max_questions_per_paper]
    return {
        "paper_id": paper_id,
        "paper_url": paper_url,
        "paper_title": paper_title,
        "question_count": len(questions),
        "questions": questions,
    }


def crawl_collection(
    collection_id: str,
    max_papers: int,
    max_questions_per_paper: int,
    max_pages: int,
    workers: int,
) -> Dict:
    paper_ids, pages_crawled = fetch_paper_ids_by_pages(collection_id, max_pages)
    if max_papers > 0:
        paper_ids = paper_ids[:max_papers]
    print(f"[INFO] Collection pages crawled: {pages_crawled}")
    print(f"[INFO] Papers found: {len(paper_ids)}")

    papers_out = []
    total_questions = 0

    if workers <= 1:
        for i, paper_id in enumerate(paper_ids, start=1):
            print(f"[INFO] ({i}/{len(paper_ids)}) Fetch paper: {paper_id}")
            paper_data = fetch_and_parse_paper(paper_id, max_questions_per_paper)
            papers_out.append(paper_data)
            total_questions += paper_data["question_count"]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(fetch_and_parse_paper, pid, max_questions_per_paper): pid
                for pid in paper_ids
            }
            done_map: Dict[str, Dict] = {}
            for future in as_completed(future_map):
                pid = future_map[future]
                try:
                    done_map[pid] = future.result()
                except Exception as e:
                    print(f"[WARN] paper {pid} failed: {e}")
            for pid in paper_ids:
                if pid in done_map:
                    papers_out.append(done_map[pid])
                    total_questions += done_map[pid]["question_count"]

    return {
        "site": "kmath.cn",
        "collection_id": collection_id,
        "collection_url": f"{BASE_URL}collection.aspx?id={collection_id}",
        "collection_pages_crawled": pages_crawled,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "paper_count": len(papers_out),
        "question_count": total_questions,
        "papers": papers_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape kmath questions (question only).")
    parser.add_argument("--collection-id", default="649", help="collection.aspx?id=...")
    parser.add_argument(
        "--output",
        default="kmath_questions.json",
        help="output JSON file path",
    )
    parser.add_argument("--max-papers", type=int, default=0, help="0 means all")
    parser.add_argument(
        "--max-questions-per-paper", type=int, default=0, help="0 means all"
    )
    parser.add_argument("--max-pages", type=int, default=0, help="0 means auto-all")
    parser.add_argument("--workers", type=int, default=12, help="paper concurrency")
    args = parser.parse_args()

    result = crawl_collection(
        collection_id=args.collection_id,
        max_papers=args.max_papers,
        max_questions_per_paper=args.max_questions_per_paper,
        max_pages=args.max_pages,
        workers=max(1, args.workers),
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[DONE] Saved: {args.output}")
    print(f"[DONE] Papers: {result['paper_count']}, Questions: {result['question_count']}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

KNOWLEDGE_BRAIN_PATH = PROJECT_ROOT / "SECOND-KNOWLEDGE-BRAIN.md"
ARCHIVE_PATH = PROJECT_ROOT / "BRAIN-ARCHIVE.md"

CRAWL_SOURCES = [
    {
        "name": "arxiv-cs.CR",
        "url": "https://arxiv.org/list/cs.CR/recent",
        "filter_keywords": [
            "llm", "agent", "sandbox", "prompt injection", "security",
            "encryption", "zero trust", "adversarial",
        ],
    },
    {
        "name": "arxiv-cs.AI",
        "url": "https://arxiv.org/list/cs.AI/recent",
        "filter_keywords": [
            "agent", "planning", "tool use", "code generation",
            "task automation", "reasoning",
        ],
    },
    {
        "name": "arxiv-cs.SE",
        "url": "https://arxiv.org/list/cs.SE/recent",
        "filter_keywords": [
            "code generation", "automated programming", "software agent",
            "test generation", "refactoring",
        ],
    },
]

PAPERS_TABLE_HEADER = "| Title | Authors | Year | Venue | DOI / arXiv | Relevance |"


class KnowledgeCrawler:
    def __init__(self) -> None:
        self._seen_ids: set[str] = set()
        self._load_existing_ids()

    async def crawl(self) -> list[dict]:
        import httpx
        from html.parser import HTMLParser

        new_papers: list[dict] = []

        for source in CRAWL_SOURCES:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(source["url"])
                    if resp.status_code != 200:
                        logger.warning(
                            "Crawler: %s returned %d", source["name"], resp.status_code
                        )
                        continue

                    papers = self._parse_arxiv(resp.text, source["filter_keywords"])
                    for paper in papers:
                        paper_id = paper.get("arxiv_id", "") or paper.get("doi", "")
                        if paper_id and paper_id not in self._seen_ids:
                            new_papers.append(paper)
                            self._seen_ids.add(paper_id)

            except Exception as exc:
                logger.warning("Crawler: %s failed: %s", source["name"], exc)

        return new_papers

    def append_to_brain(self, papers: list[dict]) -> int:
        if not papers:
            return 0

        with open(KNOWLEDGE_BRAIN_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        new_entries = []
        for paper in papers:
            row = (
                f"| {paper.get('title', 'Unknown')} "
                f"| {paper.get('authors', 'Unknown')} "
                f"| {paper.get('year', 'Unknown')} "
                f"| {paper.get('venue', 'arXiv')} "
                f"| {paper.get('arxiv_id', '')} "
                f"| {paper.get('relevance', 'Auto-crawled')} |"
            )
            new_entries.append(row)

        insertion_point = content.find("## Knowledge Update Log")
        if insertion_point == -1:
            insertion_point = content.find("*Next scheduled auto-update:")

        if insertion_point != -1:
            new_section = "\n".join(new_entries) + "\n\n"
            content = content[:insertion_point] + new_section + content[insertion_point:]

        with open(KNOWLEDGE_BRAIN_PATH, "w", encoding="utf-8") as f:
            f.write(content)

        self._update_log(len(papers))
        self._archive_if_needed()
        return len(papers)

    def _update_log(self, count: int) -> None:
        with open(KNOWLEDGE_BRAIN_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_entry = (
            f"| {now} | Automated crawl | {count} papers | KnowledgeCrawler (auto) |\n"
        )

        log_section_marker = "| Date | Source | Entries Added | Added By |"
        log_pos = content.find(log_section_marker)
        if log_pos != -1:
            table_end = content.find("\n\n", content.find("\n", log_pos + len(log_section_marker)))
            if table_end != -1:
                content = content[:table_end] + "\n" + log_entry + content[table_end:]
            else:
                content += log_entry

        with open(KNOWLEDGE_BRAIN_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    def _archive_if_needed(self) -> None:
        with open(KNOWLEDGE_BRAIN_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        paper_count = content.count("| arxiv:")
        paper_count += content.count("| DOI:")
        paper_count += content.count("| arXiv:")

        if paper_count <= 55:
            return

        if ARCHIVE_PATH.exists():
            with open(ARCHIVE_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n\n## Archived on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n")
                f.write("Papers exceeding 50-entry limit archived from SECOND-KNOWLEDGE-BRAIN.md\n")
        else:
            with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
                f.write("# BRAIN-ARCHIVE.md — SecureClawAgent Knowledge Archive\n\n")
                f.write(f"## Archived on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n")

        logger.info("Archived papers to BRAIN-ARCHIVE.md (total: %d)", paper_count)

    def _load_existing_ids(self) -> None:
        if not KNOWLEDGE_BRAIN_PATH.exists():
            return
        with open(KNOWLEDGE_BRAIN_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        for match in re.finditer(r"(?:arxiv:|arXiv:)([\w.]+)", content):
            self._seen_ids.add(f"arxiv:{match.group(1)}")
        for match in re.finditer(r"(?:DOI:|doi:)(\S+)", content):
            self._seen_ids.add(f"doi:{match.group(1)}")

    @staticmethod
    def _parse_arxiv(html: str, keywords: list[str]) -> list[dict]:
        papers: list[dict] = []
        dl_pattern = re.compile(
            r'<dt>.*?<a[^>]*href="[^"]*/(?:abs|pdf)/(\d+\.\d+)[^"]*"[^>]*>(.*?)</a>.*?</dt>'
            r'\s*<dd[^>]*>.*?<div[^>]*class="list-authors"[^>]*>(.*?)</div>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in dl_pattern.finditer(html):
            arxiv_id = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            authors_raw = re.sub(r"<[^>]+>", "", match.group(3)).strip()
            authors = re.sub(r"\s+", " ", authors_raw)[:120]

            combined = (title + " " + authors_raw).lower()
            relevance_keywords = [
                kw for kw in keywords if kw.lower() in combined
            ]

            if relevance_keywords:
                papers.append({
                    "arxiv_id": f"arxiv:{arxiv_id}",
                    "title": title[:200],
                    "authors": authors,
                    "year": f"20{arxiv_id[:2]}",
                    "venue": "arXiv",
                    "relevance": ", ".join(relevance_keywords[:3]),
                })

        return papers


_crawler_instance: Optional[KnowledgeCrawler] = None


def get_knowledge_crawler() -> KnowledgeCrawler:
    global _crawler_instance
    if _crawler_instance is None:
        _crawler_instance = KnowledgeCrawler()
    return _crawler_instance

"""Retrieval over your own documents, with no vector database.

BM25 over Arabic text, in about a hundred lines and with no model to download.
For a knowledge base of a few thousand passages — a returns policy, a handbook,
a set of operating procedures — this retrieves as well as embeddings do and
starts instantly, which matters when the alternative is a cold model load in
front of a live caller.

Three things about Arabic specifically:

* Normalisation. أ إ آ all become ا, ة becomes ه, and tashkeel is stripped —
  otherwise "الشراء" and "الشِراء" are different words to the index.
* Affixes. The definite article and the common suffixes come off at index and
  query time alike, so "الفاتورة" and "فاتورة" are one word.
* Broken plurals. Arabic does not form plurals by adding a letter — "فرع"
  becomes "فروع", with the change inside the word. Stripping affixes alone
  leaves those as two unrelated terms, which is how a question about branch
  opening hours ends up matching the escalation procedure instead. Dropping
  the internal weak letters (ا و ي) approximates the root and puts them back
  together.

None of this is a real morphological analyser. It is the cheap 90% — enough
that a policy question finds the policy, and small enough to read.

Swap this for a real vector store when the corpus grows past a few thousand
passages; `search()` is the only function anything else calls.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR", "knowledge"))

# BM25 constants. k1 controls how fast term frequency saturates, b how much
# document length is penalised. These are the usual defaults and are fine.
K1 = 1.5
B = 0.75

TASHKEEL = re.compile(r"[ً-ْٰـ]")

# \W already covers Arabic letters, so this splits on punctuation and nothing
# else. Naming the Arabic block explicitly here would be a mistake: U+0600–060F
# holds ؟ ، and ؛, and including it glues the question mark onto the last word
# of every question — which is exactly the word the question is about.
NON_WORD = re.compile(r"\W+", re.UNICODE)


@dataclass
class Passage:
    doc: str
    page: str
    text: str


@dataclass
class Hit:
    passage: Passage
    score: float

    def cite(self) -> str:
        return f"{self.passage.doc}, {self.passage.page}"


def normalise(text: str) -> str:
    text = TASHKEEL.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ى", "ي")
    return text


# Stripped from the front and back before matching. Longest first, so that
# "وال" is tried before "و".
PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
SUFFIXES = ("اتها", "اته", "ها", "هم", "ية", "يه", "ات", "ون", "ين", "ان")
WEAK = ("ا", "و", "ي")


def stem(word: str) -> str:
    """Cheap Arabic stem: strip affixes, then hollow out the weak letters."""
    for prefix in PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            word = word[len(prefix):]
            break
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    # "فروع" → "فرع", so the plural meets the singular. Only the interior is
    # touched: a weak letter at either end is often part of the root itself.
    if len(word) > 3:
        core = word[0] + "".join(c for c in word[1:-1] if c not in WEAK) + word[-1]
        if len(core) >= 3:
            word = core
    return word


def tokenise(text: str) -> list[str]:
    words = NON_WORD.split(normalise(text).lower())
    return [stem(w) for w in words if len(w) >= 2]


class Index:
    """An in-memory BM25 index over the passages found in KNOWLEDGE_DIR."""

    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages
        self.tokens = [tokenise(p.text) for p in passages]
        self.lengths = [len(t) for t in self.tokens]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.counts = [Counter(t) for t in self.tokens]

        seen = Counter()
        for tokens in self.tokens:
            seen.update(set(tokens))
        self.doc_freq = seen
        self.total = len(passages)

    def _idf(self, term: str) -> float:
        n = self.doc_freq.get(term, 0)
        if n == 0:
            return 0.0
        return math.log(1 + (self.total - n + 0.5) / (n + 0.5))

    def search(self, query: str, *, limit: int = 3) -> list[Hit]:
        terms = tokenise(query)
        scored: list[Hit] = []
        for i, counts in enumerate(self.counts):
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                norm = 1 - B + B * (self.lengths[i] / (self.avg_length or 1))
                score += self._idf(term) * (tf * (K1 + 1)) / (tf + K1 * norm)
            if score > 0:
                scored.append(Hit(passage=self.passages[i], score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]


def load(directory: Path = KNOWLEDGE_DIR) -> Index:
    """Read every .md in the knowledge directory, split on ## headings.

    A heading is used as the page marker so a citation points somewhere a
    person can actually turn to, rather than at a chunk number that means
    nothing to the caller you are reading it to.
    """
    passages: list[Passage] = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title = path.stem.replace("-", " ")
        section = ""
        buffer: list[str] = []

        def flush() -> None:
            # Anything before the first ## is the document title, not a
            # passage. Indexing it means a question about the subject of the
            # document retrieves its cover page.
            if not section:
                return
            body = "\n".join(buffer).strip()
            if body:
                passages.append(Passage(doc=title, page=section, text=body))

        for line in raw.splitlines():
            if line.startswith("## "):
                flush()
                buffer = []
                section = line[3:].strip()
            else:
                buffer.append(line)
        flush()

    if not passages:
        raise FileNotFoundError(
            f"No .md files in {directory}/ — put your documents there, or set KNOWLEDGE_DIR"
        )
    return Index(passages)


def search(query: str, *, limit: int = 3, index: Index | None = None) -> list[Hit]:
    return (index or load()).search(query, limit=limit)

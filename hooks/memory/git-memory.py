#!/usr/bin/env python3
"""
git-memory: Cross-session decision memory + file discovery for Claude Code.

Injects project context into Claude via additionalContext on every prompt.
Works on ANY git project without setup.

Modes (combinable):
  --git-only     (default) Git log only.
  --rich         Git log + .omc/world-model.json dead-ends/facts.
  --g2           Prompt keyword → codebase graph search (pre-fetch related files).

Usage in settings.json:
  "command": "python3 $HOME/.claude/hooks/git-memory.py"                    # git-only
  "command": "python3 $HOME/.claude/hooks/git-memory.py --rich --g2"        # full
"""
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys


RICH = "--rich" in sys.argv
G2 = "--g2" in sys.argv

# Vec-daemon socket (shared with chat-memory.py)
_VEC_SOCK = os.path.expanduser("~/.local/share/claude-vault/vec-daemon.sock")
_VEC_TIMEOUT = 0.5  # seconds — skip semantic if daemon slow/unavailable


def _embed_via_daemon(text):
    """Get embedding from vec-daemon. Returns list[float] or None on failure."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(_VEC_TIMEOUT)
        s.connect(_VEC_SOCK)
        s.sendall((json.dumps({"q": text}) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        resp = json.loads(buf.split(b"\n")[0])
        return resp.get("emb") if resp.get("ok") else None
    except Exception:
        return None


def _cosine_sim(a, b):
    """Cosine similarity between two pre-normalized embedding lists."""
    return sum(x * y for x, y in zip(a, b))


def _semantic_rerank(decisions, prompt_emb, alpha=0.4):
    """Rerank decisions list by semantic similarity to prompt embedding.

    Uses vec-daemon (multilingual-e5-small) to embed each commit subject,
    then reranks by hybrid: alpha * semantic + (1-alpha) * positional_prior.
    Breaks BM25's ceiling on paraphrase queries where lexical match fails.

    alpha=0.4: semantic contributes 40%, positional (BM25 pre-rank) 60%.
    Returns reranked decisions list. Falls back to original order on failure.
    """
    if not decisions or prompt_emb is None:
        return decisions
    try:
        scored = []
        for i, decision in enumerate(decisions):
            # Positional prior: BM25 rank already encoded in position (0=best)
            positional_score = 1.0 - (i / len(decisions))
            # Semantic similarity
            emb = _embed_via_daemon(decision[:200])  # truncate for speed
            if emb is None:
                semantic_score = 0.5  # neutral fallback
            else:
                semantic_score = max(0.0, _cosine_sim(prompt_emb, emb))
            hybrid = alpha * semantic_score + (1.0 - alpha) * positional_score
            scored.append((hybrid, decision))
        scored.sort(key=lambda x: -x[0])
        return [d for _, d in scored]
    except Exception:
        return decisions


def get_files_for_commit(project_dir, commit_hash):
    """Get files changed in a specific commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            cwd=project_dir, capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            return []
        return [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    except Exception:
        return []


_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".sh", ".bash", ".yaml", ".yml", ".toml", ".sql", ".css", ".html",
    ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt",
}
_SKIP_PREFIXES = (".omc/", "docs/", "benchmarks/results/", "tests/fixtures/")


def _code_files(files):
    """Filter to source-code files only (skip docs, state, benchmark results)."""
    return [
        f for f in files
        if any(f.endswith(ext) for ext in _CODE_EXT)
        and not any(f.startswith(p) for p in _SKIP_PREFIXES)
    ]


def check_temporal_validity(project_dir, commit_hash, files):
    """Check staleness and conflict using exact hash range (no self-inclusion).

    Uses `{commit_hash}..HEAD` to find commits STRICTLY AFTER the given commit,
    avoiding the date-based self-inclusion bug. Only considers code files.

    Returns:
        (mod_count, superseder_msg) where:
        - mod_count: # of commits touching code files after this commit
        - superseder_msg: subject of a newer commit that overrides this (or None)
    """
    code_files = _code_files(files)
    if not code_files:
        return 0, None
    override_keywords = [
        "revert", "replace", "switch", "abandon", "reject", "rewrite", "back to",
    ]
    try:
        args = (
            ["git", "log", f"{commit_hash}..HEAD", "--format=%s", "--"]
            + code_files
        )
        result = subprocess.run(
            args, cwd=project_dir, capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            return 0, None
        subjects = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        mod_count = len(subjects)
        superseder = next(
            (s[:60] for s in subjects if any(kw in s.lower() for kw in override_keywords)),
            None,
        )
        return mod_count, superseder
    except Exception:
        return 0, None


DECISION_CAP = 7    # maximum decisions injected per session

_CONV_PREFIXES = (
    "feat:", "fix:", "refactor:", "perf:", "security:", "design:", "test:",
    "feat(", "fix(", "refactor(", "perf(",
    "add:", "update:", "remove:", "introduce:", "implement:", "migrate:",
)
_VERSION_RE = re.compile(r"^v\d+\.\d+")
_DECISION_KEYWORDS = (
    "pivot", "revert", "dead-end", "rejected", "chose", "switched",
    "CONVERGED", "failed", "success", "fix", "improvement",
    "benchmark", "eval", "decision", "iter",
)
# Universal decision verbs matched with word boundary (avoids substring FPs like "address"→"add")
# Covers general project commits that don't use CTX-style keywords or conventional prefixes.
# Verified: \badd\b does NOT match "address", "added", "additional" etc.
_DECISION_VERBS_RE = re.compile(
    r"\b(add|added|adds|use[ds]?|remove[ds]?|replac[eing]+|introduc[eing]+|"
    r"migrat[eing]+|implement[ings]*|deprecat[eing]+|drop(?:ped|s)?|"
    r"support[sing]*|updat[eing]+|relax(?:ed|es)?|address(?:ed|es)?|"
    r"enforce[ds]?|allow[sing]*|prevent[sing]*|extend[sing]*|simplif[ying]+)\b",
    re.IGNORECASE
)
_NOISE_PREFIXES = ("# ", "wip:", "merge ", "revert \"")

# Structural noise filters — version bumps and iteration checkpoints crowd the 7-cap
_STRICT_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+")   # strict semver: v3.42.4
_OMC_ITER_RE = re.compile(r"^(omc-live|live-inf)\s+iter", re.IGNORECASE)
# Embedded decision: "v3.42.4 - fix: /live IP list" → preserved (has real content)
_EMBEDDED_DECISION_RE = re.compile(
    r"\s[-—]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
    re.IGNORECASE
)

# Synonym/alias map: maps acronyms/abbreviations → searchable commit-message terms.
# Fixes keyword-poor miss cases where prompt uses high-level terms not in commit subjects.
# Keys are matched case-insensitively. Values are injected as extra Pass0 grep targets.
_SYNONYM_MAP = {
    # Acronyms: expand abbreviations to commit-searchable terms
    "COIR": ["corpus", "retrieval"],
    "BM25": ["okapi", "ranking"],
    "SOTA": ["baseline", "comparison"],
    "G1": ["git-memory", "decision"],
    "G2": ["prefetch", "graph"],
    "CTX": ["context", "bootstrap"],
    "LLM": ["language", "model"],
    "RAG": ["retrieval", "generation"],
    "EVAL": ["evaluation", "benchmark"],
    "OMC": ["autopilot", "live"],
    "ITER": ["iteration", "step"],
    # Action/domain synonyms: bridge paraphrase gap for common action verbs
    # Domain-agnostic — applies to Flask/Requests/Django equally
    "LEGACY": ["old", "deprecated"],          # "legacy X" → "Old X removed"
    "CLEANUP": ["remove", "delete"],          # "cleaned up" → "removed"
    "PERFORMANCE": ["benchmark", "speedup"],  # "performance boost" → "benchmark"
    "LAUNCH": ["deploy", "release", "ship"],  # "launched" → "released/deployed"
    "REFACTOR": ["restructure", "reorganize", "cleanup"],  # "refactored" → "restructured"
    "OPTIMIZE": ["speedup", "improve", "perf"],  # "optimized" → "speedup/improve"
}

# Temporal evolution query detection.
# Queries about "how X changed over time" → chronological output mode.
_TEMPORAL_QUERY_RE = re.compile(
    r"\b(progression|evolution|history|timeline|over\s+time|before\s+(and\s+)?after|"
    r"how\s+\w+\s+changed?|changes?\s+over|chronolog|sequence|trend|했나|변화|"
    r"이력|진행|순서|발전)\b",
    re.IGNORECASE
)


def _is_structural_noise(subject):
    """True if commit is version bump or iteration checkpoint (not a real topic decision).

    Exception: version tags with embedded decision content like
    "v3.42.4 - fix: /live IP list" are preserved.
    """
    s = subject.strip()
    if _OMC_ITER_RE.match(s):
        return True
    if _STRICT_VERSION_RE.match(s):
        # Keep if there's an embedded decision after the version number
        return not bool(_EMBEDDED_DECISION_RE.search(s))
    return False


def _is_decision(subject):
    """Universal decision-commit detector: conventional commits + version + keywords."""
    s = subject.strip()
    if not s:
        return False
    sl = s.lower()
    # Skip noise (boilerplate lines, WIP, merge commits)
    if any(sl.startswith(p) for p in _NOISE_PREFIXES):
        return False
    # Conventional commit prefix (feat:, fix:, refactor:, perf:, etc.)
    if any(sl.startswith(p) for p in _CONV_PREFIXES):
        return True
    # Version-tagged commit (v1.0.0, v3.42.4 …)
    if _VERSION_RE.match(s):
        return True
    # Legacy / CTX-style keywords
    if any(kw.lower() in sl for kw in _DECISION_KEYWORDS):
        return True
    # Universal verbs (word-boundary): add, remove, update, introduce, etc.
    # Covers general projects (Flask, Django) that don't use CTX-style keywords.
    return bool(_DECISION_VERBS_RE.search(sl))


def _topic_key(files):
    """Cluster key from code files — frozenset of top-2 code file paths."""
    code = [f for f in files
            if f.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs"))
            and not f.startswith(("tests/", "test_", "docs/"))]
    return frozenset(sorted(code)[:2]) if code else None


def _bm25_rank_by_prompt(candidates, prompt_keywords):
    """Re-rank decision candidates by BM25 relevance to prompt keywords.

    Uses rank_bm25.BM25Okapi to score each commit subject against the
    prompt keywords. Falls back to original order on any failure.

    Why: recency-only selection yields G1 recall=0.169; BM25 re-ranking
    closes the gap toward the BM25 benchmark ceiling (Recall@7=0.881).
    """
    if not prompt_keywords or len(candidates) < 3:
        return candidates
    try:
        from rank_bm25 import BM25Okapi
        tokenized_corpus = [
            re.findall(r'[a-zA-Z가-힣][a-zA-Z0-9가-힣]*', c["subject"].lower())
            for c in candidates
        ]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores([k.lower() for k in prompt_keywords])
        indexed = sorted(enumerate(scores), key=lambda x: -x[1])
        return [candidates[i] for i, _ in indexed]
    except Exception:
        return candidates


def get_git_decisions(project_dir, n=30, prompt_keywords=None, temporal_mode=False):
    """Extract decision-bearing commits from git log with temporal annotations.

    n=30 to scan past version-bump blocks in active versioned projects.
    Three-pass algorithm + deep keyword grep:
      Pass 0: git log --grep for each keyword → surface deep-history decisions
      Pass 1: collect all non-noise decision candidates in the n-window
      Pass 1.5: BM25 re-rank by prompt relevance (if keywords available)
      Pass 2: topic-dedup selection — 1 most-relevant per topic cluster
    Pass 0 (deep grep) closes the history coverage gap for keyword queries:
    relevant commits at positions 30-200+ are found via full-history grep.

    temporal_mode=True: skip BM25 rerank, sort chronologically (oldest-first),
    prefix each decision with [YYYY-MM-DD]. Used for evolution/history queries.
    """
    # Pass 0: Deep keyword grep — surface commits beyond the n-window
    deep_candidates = {}  # hash → subject, to merge with Pass 1
    if prompt_keywords:
        # Base keywords: ≥4 chars alphabetic (original)
        long_kws = [k for k in prompt_keywords
                    if len(k) >= 4 and re.match(r'[a-zA-Z]', k)][:3]
        # Extra Pass 0 targets from keywords list (already enriched by extract_keywords):
        # - hyphenated compounds (len ≥ 6, contains '-')
        # - 4-digit numeric tokens (session timestamps like "2040", "1930")
        # - 3-char alphabetic tokens not in long_kws (acronyms like "CTX", "omc")
        compound_kws = [k for k in prompt_keywords if '-' in k and len(k) >= 6][:2]
        numeric_kws = [k for k in prompt_keywords if re.match(r'^\d{4,}$', k)][:2]
        short_kws = [k for k in prompt_keywords
                     if len(k) == 3 and re.match(r'[a-zA-Z]', k) and k not in long_kws][:1]
        extra_kws = compound_kws + numeric_kws + short_kws
        grep_kws = long_kws + [k for k in extra_kws if k not in long_kws]
        for kw in grep_kws[:5]:
            try:
                r = subprocess.run(
                    ["git", "log", "--format=%H\x1f%s", f"--grep={kw}",
                     "-i", "--max-count=10"],
                    cwd=project_dir, capture_output=True, text=True, timeout=3
                )
                for line in r.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.strip().split("\x1f", 1)
                    if len(parts) == 2:
                        h, subj = parts
                        # Pass 0: grep is the relevance signal — only filter structural noise.
                        # _is_decision() is NOT applied here: many valid general-project
                        # commits (e.g., "request context tracks session access") don't
                        # match CTX-style keywords but are surfaced correctly by grep.
                        if h and not _is_structural_noise(subj):
                            deep_candidates[h] = subj[:120]
            except Exception:
                pass

    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H\x1f%s\x1f%ai"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return [], []
    except Exception:
        return [], []

    # Pass 1: collect candidates and work items
    candidates, work = [], []
    seen_subjects = set()
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 2)
        subject = parts[1] if len(parts) == 3 else line.strip()[:120]
        commit_hash = parts[0] if len(parts) == 3 else ""
        date_str = parts[2][:10] if len(parts) == 3 else ""  # YYYY-MM-DD

        if len(subject) > 120:
            cut = subject[:120].rfind(" ")
            subject = subject[:cut] if cut > 80 else subject[:120]

        if _is_structural_noise(subject):
            continue

        subject_key = subject[:60]
        if subject_key in seen_subjects:
            continue
        seen_subjects.add(subject_key)

        if _is_decision(subject):
            candidates.append({"hash": commit_hash, "subject": subject, "date": date_str})
        elif len(work) < 3:
            work.append(subject)

    # Merge deep_candidates: inject at end (lowest recency priority, BM25 will re-rank)
    existing_hashes = {c["hash"] for c in candidates}
    for h, subj in deep_candidates.items():
        if h not in existing_hashes:
            candidates.append({"hash": h, "subject": subj, "date": ""})

    if not candidates:
        return [], work[:3]

    # Pass 1.5: BM25 re-rank by prompt relevance (prompt-aware selection)
    # Reorders candidates from newest-first → most-relevant-first.
    # Topic-dedup in Pass 2 then selects the best commit per topic cluster.
    # Skipped for temporal_mode: preserve chronological order (git log = newest-first →
    # will be reversed after Pass 2 to show oldest-first evolution).
    if prompt_keywords and not temporal_mode:
        candidates = _bm25_rank_by_prompt(candidates, prompt_keywords)

    # Pass 2: topic-dedup selection — get files for first 2×cap candidates
    scan_limit = min(DECISION_CAP * 2, len(candidates))
    for c in candidates[:scan_limit]:
        c["files"] = get_files_for_commit(project_dir, c["hash"]) if c["hash"] else []
        c["topic"] = _topic_key(c["files"])

    # Select: 1 newest per topic cluster (topic-aware dedup), then fill remainder
    selected = []
    seen_topics = set()
    remainder = []
    for c in candidates[:scan_limit]:
        tk = c.get("topic")
        if tk is not None and tk not in seen_topics:
            seen_topics.add(tk)
            selected.append(c)
        else:
            remainder.append(c)

    for c in remainder:
        if len(selected) >= DECISION_CAP:
            break
        selected.append(c)

    # Fallback: fill from beyond scan_limit if still under cap
    if len(selected) < DECISION_CAP:
        for c in candidates[scan_limit:]:
            if len(selected) >= DECISION_CAP:
                break
            c.setdefault("files", [])
            c.setdefault("topic", None)
            selected.append(c)

    # Temporal mode: sort oldest-first for evolution/history queries
    if temporal_mode:
        # git log output is newest-first; reverse so timeline reads chronologically
        selected = list(reversed(selected))

    # Pass 3: annotate final top-7 with temporal validity
    decisions = []
    for c in selected[:DECISION_CAP]:
        annotation = c["subject"]
        files = c.get("files") or (get_files_for_commit(project_dir, c["hash"]) if c["hash"] else [])
        if files:
            mod_count, superseder = check_temporal_validity(
                project_dir, c["hash"], files
            )
            if superseder:
                annotation += f" [superseded: {superseder}]"
            elif mod_count > 0:
                annotation += f" [possibly outdated — modified {mod_count}x since]"
        # Prefix date for temporal mode
        date_prefix = f"[{c['date']}] " if temporal_mode and c.get("date") else ""
        decisions.append(f"{date_prefix}{annotation}"[:180])

    return decisions[:DECISION_CAP], work[:3]


def get_world_model(project_dir):
    """Load dead-ends and facts from world-model.json."""
    wm_path = os.path.join(project_dir, ".omc", "world-model.json")
    if not os.path.exists(wm_path):
        return [], []
    try:
        with open(wm_path) as f:
            wm = json.load(f)
    except Exception:
        return [], []

    dead_ends = [f"  x {de.get('goal','')[:60]} -- {de.get('reason','')[:80]}"
                 for de in wm.get("dead_ends", [])[-5:]]
    facts = []
    for fact in wm.get("known_facts", []):
        if isinstance(fact, dict):
            facts.append(f"  * {fact['fact'][:80]}")
        elif isinstance(fact, str) and not any(fact.startswith(p) for p in ("paper:", "README:", "uncertain:")):
            facts.append(f"  * {fact[:80]}")
    return dead_ends, facts[-8:]


def get_session_decisions(project_dir: str) -> list:
    """Read .omc/session-decisions.md for uncommitted decisions."""
    from pathlib import Path
    decisions_file = Path(project_dir) / ".omc" / "session-decisions.md"
    if not decisions_file.exists():
        return []
    try:
        lines = decisions_file.read_text().strip().split("\n")
        # Return lines starting with ">" (decision entries), last 5
        entries = [l.strip() for l in lines if l.strip().startswith(">")]
        return entries[-5:]  # most recent 5
    except Exception:
        return []


def get_project_overview(project_dir):
    """Extract first line from CLAUDE.md or README.md."""
    for fname in ["CLAUDE.md", "README.md"]:
        fpath = os.path.join(project_dir, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("---"):
                            return line[:100]
            except Exception:
                pass
    return None


# ── G2: Prompt → Graph Search ──────────────────────────────────

def find_db(project_dir):
    """Find codebase-memory-mcp SQLite DB."""
    cache_dir = os.path.expanduser("~/.cache/codebase-memory-mcp")
    if not os.path.isdir(cache_dir):
        return None
    slug = project_dir.replace("/", "-").lstrip("-")
    db_path = os.path.join(cache_dir, f"{slug}.db")
    if os.path.exists(db_path):
        return db_path
    for f in os.listdir(cache_dir):
        if f.endswith(".db") and os.path.basename(project_dir).lower() in f.lower():
            return os.path.join(cache_dir, f)
    return None


def extract_keywords(prompt):
    """Extract meaningful keywords from user prompt for graph search."""
    stop = {"the","a","an","is","are","was","were","be","been","being","have","has","had",
            "do","does","did","will","would","could","should","may","might","shall","can",
            "to","of","in","for","on","with","at","by","from","as","into","through",
            "it","this","that","these","those","i","you","he","she","we","they","me",
            "and","or","but","not","no","if","then","else","when","where","how","what",
            "which","who","whom","why","all","each","every","both","few","more","most",
            "해줘","해","바람","좀","것","수","있","없","하다","되다","이","그","저","뭐","어떻게",
            "기능","작업","관련","파일","코드","문서","수정","추가","변경","확인","돌려봐",
            "올려","실행","해봐","분석","개선","확인해"}
    # Korean concept → English code mapping (common dev terms)
    ko_en = {
        # CTX/ML specific
        "검색": "search,retrieve,find", "엔진": "engine,retriever",
        "벤치마크": "benchmark,eval", "평가": "eval,evaluate",
        "트리거": "trigger", "분류": "classify,classifier",
        "밀도": "dense,density", "테스트": "test",
        "결과": "result", "스코어": "score",
        "임포트": "import", "그래프": "graph",
        "다운스트림": "downstream", "스페이스": "space,app",
        "외부": "external,reeval", "정확도": "accuracy,precision",
        # General webapp/dev terms
        "이메일": "email,mail", "발송": "send,outreach",
        "대시보드": "dashboard,admin", "구독": "subscription,subscribe",
        "인증": "auth,authenticate", "로그인": "login,signin",
        "사용자": "user,member", "데이터베이스": "database,schema",
        "함수": "function,handler", "컴포넌트": "component",
        "페이지": "page,route", "설정": "config,settings",
        "환경": "env,environment", "서버": "server,backend",
        "실험": "experiment,trial", "패러다임": "paradigm",
        "적응": "adapt,adaptation", "배포": "deploy,deployment",
        "오류": "error,exception", "버그": "bug,error",
        "성능": "performance,latency", "최적화": "optimize,cache",
        "알림": "notification,alert", "권한": "permission,auth",
    }
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}|[가-힣]{2,}', prompt)
    keywords = []
    for w in words:
        if w.lower() in stop:
            continue
        if len(w) < 2:
            continue
        # Korean → English expansion
        if re.match(r'[가-힣]', w) and w in ko_en:
            keywords.extend(ko_en[w].split(","))
        else:
            keywords.append(w)

    # Pass 0 enrichment: hyphenated compounds and numeric tokens
    # These are high-specificity grep targets not captured by word tokenization.
    # "git-memory" → hyphen is not in [a-zA-Z0-9_] so tokenizer splits it.
    # "2040" → numeric token for session timestamps / versioned identifiers.
    compound_terms = re.findall(r'[a-zA-Z]{3,}-[a-zA-Z0-9]{2,}', prompt)
    numeric_tokens = re.findall(r'\b\d{4,}\b', prompt)
    for t in compound_terms + numeric_tokens:
        if t not in keywords:
            keywords.append(t)

    # Synonym expansion: map acronyms/abbreviations → commit-message-searchable terms.
    # E.g. "COIR" → ["corpus", "retrieval"], "SOTA" → ["baseline", "comparison"].
    # Injected as extra Pass0 grep targets; fixes keyword-poor miss cases.
    for w in list(keywords):
        syns = _SYNONYM_MAP.get(w.upper())
        if syns:
            for syn in syns:
                if syn not in keywords:
                    keywords.append(syn)

    return keywords[:12]  # +2 slots vs. previous :10 to accommodate synonym expansion


def search_files_by_grep(project_dir, keywords, limit=5):
    """Fallback file discovery via git grep when no graph DB is available.

    Uses git grep -c (count) to rank files by number of keyword matches —
    files that match more keywords appear first.
    """
    long_kws = [k for k in keywords if len(k) >= 4 and not re.match(r'[가-힣]', k)]
    if not long_kws:
        return []
    try:
        pattern = "|".join(re.escape(k) for k in long_kws[:4])
        result = subprocess.run(
            ["git", "grep", "-c", "-E", "-i", "--", pattern],
            cwd=project_dir, capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            return []
        # Output format: "filepath:count" — parse and sort by count desc
        scored = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                fpath, count = line.rsplit(":", 1)
                scored.append((int(count), fpath.strip()))
            except ValueError:
                continue
        scored.sort(key=lambda x: -x[0])
        files = [f for _, f in scored]
        return _code_files(files)[:limit]
    except Exception:
        return []


def search_graph_for_prompt(db_path, keywords, limit=5):
    """Search codebase graph nodes + file paths matching prompt keywords."""
    if not keywords:
        return []
    try:
        db = sqlite3.connect(db_path)
        results = []
        seen = set()
        for kw in keywords:
            # Search node names (Function/Method/Class)
            rows = db.execute(
                "SELECT DISTINCT label, name, file_path FROM nodes "
                "WHERE name LIKE ? AND label IN ('Function','Method','Class') "
                "ORDER BY length(name) ASC LIMIT ?",
                (f"%{kw}%", 3)
            ).fetchall()
            for r in rows:
                key = (r[1], r[2])
                if key not in seen:
                    seen.add(key)
                    results.append(r)
            # Search file paths (catches benchmark scripts, config files)
            if len(results) < limit:
                frows = db.execute(
                    "SELECT DISTINCT label, name, file_path FROM nodes "
                    "WHERE file_path LIKE ? AND label IN ('Module','File') "
                    "ORDER BY length(file_path) ASC LIMIT ?",
                    (f"%{kw}%", 2)
                ).fetchall()
                for r in frows:
                    key = (r[1], r[2])
                    if key not in seen:
                        seen.add(key)
                        results.append(r)
        db.close()
        return results[:limit]
    except Exception:
        return []


# ── Main ───────────────────────────────────────────────────────

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    prompt = input_data.get("prompt", "")
    lines = []

    # 0. Session decisions (uncommitted G1 notes) — prepend before git decisions
    session_notes = get_session_decisions(project_dir)

    # 1. Project overview
    overview = get_project_overview(project_dir)
    if overview:
        lines.append(f"[PROJECT] {overview}")

    # 2. Git decisions — BM25 ranked, then semantic reranked via vec-daemon
    _g1_keywords = extract_keywords(prompt) if prompt else None
    # Temporal mode: queries about "history/progression/evolution over time"
    # → skip BM25 rerank, sort chronologically, prefix with dates
    _temporal_mode = bool(prompt and _TEMPORAL_QUERY_RE.search(prompt))
    decisions, work = get_git_decisions(
        project_dir, n=30, prompt_keywords=_g1_keywords, temporal_mode=_temporal_mode
    )

    # Semantic reranking: embed prompt once, rerank by hybrid score
    # Breaks BM25 ceiling on paraphrase queries. Graceful fallback on daemon unavailable.
    # Skip in temporal_mode: chronological order must be preserved.
    if decisions and prompt and not _temporal_mode:
        _prompt_emb = _embed_via_daemon("query: " + prompt[:500])
        if _prompt_emb:
            decisions = _semantic_rerank(decisions, _prompt_emb, alpha=0.4)

    if decisions:
        header = "[DECISION TIMELINE]" if _temporal_mode else "[RECENT DECISIONS (BM25+semantic)]"
        lines.append(header)
        for d in decisions:
            lines.append(f"  > {d}")
    if work:
        lines.append("[RECENT WORK]")
        for w in work:
            lines.append(f"  - {w}")

    # 3. World-model (--rich)
    if RICH:
        dead_ends, facts = get_world_model(project_dir)
        if dead_ends:
            lines.append("[DEAD-ENDS -- do not retry]")
            lines.extend(dead_ends)
        if facts:
            lines.append("[KNOWN FACTS]")
            lines.extend(facts)

    # 4. G2: Prompt → Graph pre-fetch (--g2)
    if G2 and prompt:
        db_path = find_db(project_dir)
        keywords = extract_keywords(prompt)
        if db_path and keywords:
            results = search_graph_for_prompt(db_path, keywords)
            if results:
                lines.append(f"[G2-PREFETCH] Related code for '{' '.join(keywords[:3])}':")
                seen_files = set()
                for label, name, fpath in results:
                    lines.append(f"  {label}: {name} @ {fpath}")
                    seen_files.add(fpath)
                if seen_files:
                    lines.append(f"  Start with: {', '.join(sorted(seen_files)[:3])}")
                # G2a: 1-hop import dependency expansion
                # For each found Python file, surface files that import it (reverse deps).
                # Helps Claude navigate to callers/dependents without extra grep turns.
                expanded = set()
                for fpath in list(seen_files)[:4]:  # limit to avoid slow runs
                    if not fpath.endswith(".py"):
                        continue
                    mod_name = os.path.splitext(os.path.basename(fpath))[0]
                    try:
                        r = subprocess.run(
                            ["git", "grep", "-l", "-E",
                             f"(import|from)\\s+[a-zA-Z0-9_.]*{re.escape(mod_name)}"],
                            cwd=project_dir, capture_output=True, text=True, timeout=2
                        )
                        for hit in r.stdout.strip().split("\n"):
                            hit = hit.strip()
                            if hit and hit not in seen_files and hit.endswith(".py"):
                                expanded.add(hit)
                    except Exception:
                        pass
                if expanded:
                    exp_sorted = sorted(expanded)[:3]
                    lines.append(f"  [G2a importers] {', '.join(exp_sorted)}")
        elif keywords:
            # Fallback: git grep for file discovery (no graph DB)
            files = search_files_by_grep(project_dir, keywords)
            if files:
                lines.append(f"[G2-GREP] Files matching '{' '.join(keywords[:3])}' (grep fallback):")
                for f in files:
                    lines.append(f"  {f}")
                lines.append(f"  Start with: {', '.join(files[:3])}")

    if session_notes:
        lines.insert(0, "[SESSION NOTES (미커밋 판단)]\n" + "\n".join(session_notes))

    if lines:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n".join(lines)
            }
        }
        json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()

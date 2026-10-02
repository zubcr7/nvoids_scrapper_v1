"""Hybrid Retrieval Engine combining BM25 and Semantic Matching via Reciprocal Rank Fusion (RRF).

Implements:
1. Okapi BM25 for exact keyword & version matching (Java 17, Spring Batch, Kafka Streams).
2. Semantic n-gram passage retrieval for descriptive experience matches.
3. Reciprocal Rank Fusion (RRF, k=60) to merge ranked lists across scales.
"""
import re
import math
from collections import Counter
from typing import List, Dict, Any, Tuple, Set

from src.parser import StructuredResume
from src.jd_decomposer import StructuredJobDescription

class BM25Okapi:
    """Pure-Python Okapi BM25 implementation."""
    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lengths = [len(doc) for doc in corpus]
        self.avg_doc_len = sum(self.doc_lengths) / max(1, self.corpus_size)
        self.doc_freqs: Dict[str, int] = Counter()
        self.doc_term_freqs: List[Dict[str, int]] = []

        for doc in corpus:
            tf = Counter(doc)
            self.doc_term_freqs.append(tf)
            for term in tf.keys():
                self.doc_freqs[term] += 1

        self.idf: Dict[str, float] = {}
        for term, freq in self.doc_freqs.items():
            # Standard Lucene/BM25 IDF
            self.idf[term] = math.log(1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5))

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        """Compute BM25 scores for query across all documents."""
        scores = [0.0] * self.corpus_size
        for term in query_tokens:
            if term not in self.idf:
                continue
            idf = self.idf[term]
            for idx, tf_dict in enumerate(self.doc_term_freqs):
                freq = tf_dict.get(term, 0)
                if freq == 0:
                    continue
                num = freq * (self.k1 + 1.0)
                den = freq + self.k1 * (1.0 - self.b + self.b * (self.doc_lengths[idx] / self.avg_doc_len))
                scores[idx] += idf * (num / den)
        return scores


class SemanticMatcher:
    """Semantic matching engine using character and word subword context vectors."""
    @staticmethod
    def tokenize(text: str) -> List[str]:
        # Preserve meaningful tokens: c++, .net, java 17, etc.
        t = text.lower()
        t = re.sub(r'[^a-z0-9+#.\s]', ' ', t)
        return [w for w in t.split() if len(w) > 1]

    @classmethod
    def get_subword_vector(cls, text: str) -> Dict[str, float]:
        """Generate subword 3-gram and 4-gram context vector for semantic matching."""
        tokens = cls.tokenize(text)
        vec: Dict[str, float] = Counter()
        # Word tokens
        for w in tokens:
            vec[f"w_{w}"] += 2.0
            # Subwords
            if len(w) >= 3:
                for i in range(len(w) - 2):
                    vec[f"ng_{w[i:i+3]}"] += 0.5
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}

    @classmethod
    def cosine_similarity(cls, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Compute cosine similarity between two sparse subword vectors."""
        dot = sum(val * vec2.get(k, 0.0) for k, val in vec1.items())
        return max(0.0, min(1.0, dot))


class HybridRetriever:
    """Orchestrates BM25 + Semantic Search + Reciprocal Rank Fusion."""
    def __init__(self, resumes: List[StructuredResume], rrf_k: int = 60):
        self.resumes = resumes
        self.rrf_k = rrf_k
        self._build_index()

    def _build_index(self):
        """Pre-index resume tokenized texts and semantic vectors."""
        self.corpus_tokens = []
        self.semantic_vectors = []

        for r in self.resumes:
            # Aggregate all passages + focus title
            doc_text = f"{r.focus_title}\n" + "\n".join(p.text for p in r.passages)
            tokens = SemanticMatcher.tokenize(doc_text)
            self.corpus_tokens.append(tokens)
            self.semantic_vectors.append(SemanticMatcher.get_subword_vector(doc_text))

        self.bm25 = BM25Okapi(self.corpus_tokens)

    def retrieve_and_rank(self, job: StructuredJobDescription) -> List[Tuple[StructuredResume, float]]:
        """Rank all resumes using Reciprocal Rank Fusion over BM25 and Semantic searches."""
        query_text = f"{job.title}\n" + " ".join(r.name for r in job.requirements)
        query_tokens = SemanticMatcher.tokenize(query_text)
        query_vec = SemanticMatcher.get_subword_vector(query_text)

        # 1. BM25 Scores & Ranks
        bm25_scores = self.bm25.get_scores(query_tokens)
        bm25_ranked_indices = sorted(range(len(self.resumes)), key=lambda i: bm25_scores[i], reverse=True)
        bm25_ranks = {idx: rank for rank, idx in enumerate(bm25_ranked_indices, start=1)}

        # 2. Semantic Similarity Scores & Ranks
        semantic_scores = [
            SemanticMatcher.cosine_similarity(query_vec, doc_vec)
            for doc_vec in self.semantic_vectors
        ]
        semantic_ranked_indices = sorted(range(len(self.resumes)), key=lambda i: semantic_scores[i], reverse=True)
        semantic_ranks = {idx: rank for rank, idx in enumerate(semantic_ranked_indices, start=1)}

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF(d) = 1 / (k + rank_bm25) + 1 / (k + rank_semantic)
        scored_resumes = []
        for idx, resume in enumerate(self.resumes):
            r_bm25 = bm25_ranks[idx]
            r_sem = semantic_ranks[idx]
            rrf_score = (1.0 / (self.rrf_k + r_bm25)) + (1.0 / (self.rrf_k + r_sem))
            scored_resumes.append((resume, rrf_score))

        # Sort descending by RRF score
        scored_resumes.sort(key=lambda x: x[1], reverse=True)
        return scored_resumes

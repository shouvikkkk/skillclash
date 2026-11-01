"""TF-IDF cosine similarity over skill names + descriptions.

Standard library only. Tokens are lowercased alphanumeric words split on
non-word characters (so ``api-helper`` becomes ``api`` + ``helper``),
filtered through a small English stopword list. IDF uses add-one
smoothing so a term seen in every document still carries some weight.
"""

from __future__ import annotations

import math
import re

STOPWORDS = frozenset(
    """
    a an the and or of to in on for with by at from as is are was were be
    been being it its this that these those you your we our they their he
    she his her do does did not no yes if then than so such into over
    under between through during before after above below up down out
    off again further once here there when where which who whom how what
    all any both each few more most other some own same too very can
    will just should now use using used via per
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text):
    """Lowercase word tokens with stopwords removed."""
    return [tok for tok in _TOKEN.findall((text or "").lower()) if tok not in STOPWORDS]


def _tfidf_vectors(documents):
    """Return (vectors, norms) for a list of token lists."""
    doc_count = len(documents)
    doc_freq = {}
    for tokens in documents:
        for tok in set(tokens):
            doc_freq[tok] = doc_freq.get(tok, 0) + 1
    vectors = []
    for tokens in documents:
        counts = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        vec = {}
        for tok, count in counts.items():
            idf = math.log((doc_count + 1) / (doc_freq[tok] + 1)) + 1.0
            vec[tok] = count * idf
        vectors.append(vec)
    norms = [math.sqrt(sum(v * v for v in vec.values())) for vec in vectors]
    return vectors, norms


def cosine(a, b, norm_a, norm_b):
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(weight * b.get(tok, 0.0) for tok, weight in a.items())
    return dot / (norm_a * norm_b)


def pairwise_similarities(documents):
    """Similarity matrix for documents (each a token list)."""
    vectors, norms = _tfidf_vectors(documents)
    matrix = [[0.0] * len(documents) for _ in documents]
    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            sim = cosine(vectors[i], vectors[j], norms[i], norms[j])
            matrix[i][j] = matrix[j][i] = sim
    return matrix


def query_scores(query_tokens, documents):
    """Cosine score of a query against each document's tokens.

    The query is scored in the same TF-IDF space as the documents: IDF
    comes from the document collection, query term frequency is 1 per
    distinct token (repeated query words do not inflate the score).
    """
    vectors, norms = _tfidf_vectors(documents)
    doc_count = len(documents)
    doc_freq = {}
    for tokens in documents:
        for tok in set(tokens):
            doc_freq[tok] = doc_freq.get(tok, 0) + 1
    qvec = {}
    for tok in set(query_tokens):
        idf = math.log((doc_count + 1) / (doc_freq.get(tok, 0) + 1)) + 1.0
        qvec[tok] = idf
    qnorm = math.sqrt(sum(v * v for v in qvec.values()))
    return [cosine(qvec, vec, qnorm, norm) for vec, norm in zip(vectors, norms)]

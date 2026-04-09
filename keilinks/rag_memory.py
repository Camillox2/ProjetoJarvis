"""
Memória de longo prazo com RAG (Retrieval-Augmented Generation).
Usa ChromaDB + embeddings para recuperar contexto de conversas antigas
por similaridade semântica.

Toda mensagem é indexada. Quando o usuário faz uma pergunta,
busca contexto relevante de qualquer conversa passada.
"""

import hashlib
import time
import re
from typing import Optional
from keilinks.log import get_logger

log = get_logger("rag")

_COLLECTION_NAME = "keilinks_memory"
_GENERIC_QUERY_PATTERNS = (
    "como você está", "como voce está", "como você tá", "como voce tá",
    "como é que você tá", "como e que voce ta", "como é que você está", "como e que voce esta",
    "tudo bem", "tudo bom", "oi", "ei", "hey", "fui", "falou", "tchau",
)


class RAGMemory:
    def __init__(self, persist_dir: str = "memoria/chromadb"):
        self._client = None
        self._collection = None
        self._ok = False
        self._persist_dir = persist_dir
        self._init_db()

    def _init_db(self):
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            count = self._collection.count()
            self._ok = True
            log.info("RAG pronto — %d documentos indexados.", count)

        except ImportError:
            log.info("chromadb não instalado. RAG desativado.")
        except Exception as e:
            log.warning("Erro ao inicializar ChromaDB: %s", e)

    @property
    def available(self) -> bool:
        return self._ok

    # ─── Indexar mensagem ─────────────────────────────────────────────────────
    def add(self, text: str, role: str = "user", metadata: dict | None = None):
        """
        Adiciona uma mensagem ao índice vetorial.
        O ChromaDB gera embeddings automaticamente (default model).
        """
        if not self._ok or not text.strip():
            return

        doc_id = hashlib.md5(f"{time.time()}:{text[:50]}".encode()).hexdigest()

        meta = {
            "role":      role,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if metadata:
            meta.update(metadata)

        try:
            self._collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )
        except Exception as e:
            log.error("Erro ao indexar no RAG: %s", e)

    # ─── Busca semântica ──────────────────────────────────────────────────────
    def query(self, text: str, n_results: int = 5,
              role_filter: str | None = None) -> list[dict]:
        """
        Busca os trechos mais relevantes por similaridade semântica.
        Retorna lista de dicts com 'text', 'role', 'timestamp', 'distance'.
        """
        if not self._ok:
            return []

        try:
            where = {"role": role_filter} if role_filter else None
            results = self._collection.query(
                query_texts=[text],
                n_results=n_results,
                where=where,
            )

            items = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    dist = results["distances"][0][i] if results["distances"] else 0.0
                    items.append({
                        "text":      doc,
                        "role":      meta.get("role", "?"),
                        "timestamp": meta.get("timestamp", "?"),
                        "distance":  dist,
                    })
            return items

        except Exception as e:
            log.error("Erro na busca RAG: %s", e)
            return []

    def query_for_prompt(self, text: str, n_results: int = 5) -> str:
        """
        Busca contexto relevante e formata para incluir no prompt do LLM.
        """
        normalized_query = re.sub(r"\s+", " ", text.lower()).strip(" !?.,;:")
        if len(normalized_query.split()) <= 3:
            return ""
        if any(p in normalized_query for p in _GENERIC_QUERY_PATTERNS):
            return ""

        items = self.query(text, n_results=n_results)
        if not items:
            return ""

        # Filtra resultados muito distantes e evita eco da própria frase atual.
        relevant = []
        for it in items:
            doc_norm = re.sub(r"\s+", " ", it["text"].lower()).strip(" !?.,;:")
            if doc_norm == normalized_query:
                continue
            if it["distance"] < 0.65:
                relevant.append(it)
        if not relevant:
            return ""

        lines = []
        for it in relevant:
            prefix = "Usuário" if it["role"] == "user" else "Keilinks"
            lines.append(f"[{it['timestamp']}] {prefix}: {it['text']}")

        return (
            "\n─── MEMÓRIA DE LONGO PRAZO (conversas passadas relevantes) ──────\n"
            + "\n".join(lines)
        )

    # ─── Stats ────────────────────────────────────────────────────────────────
    def count(self) -> int:
        if not self._ok:
            return 0
        return self._collection.count()

    def clear(self):
        if not self._ok:
            return
        try:
            self._client.delete_collection(_COLLECTION_NAME)
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            log.info("RAG limpo.")
        except Exception as e:
            log.error("Erro ao limpar RAG: %s", e)

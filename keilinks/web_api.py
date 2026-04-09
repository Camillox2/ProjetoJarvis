"""
Interface Web da Keilinks — FastAPI backend.
Roda em thread separada na porta 7865.
Fornece: histórico, stats, config, notas, RAG search.
Serve o front-end React estático de web/dist/.
"""

import threading
import json
from datetime import datetime
from pathlib import Path
from keilinks.log import get_logger

log = get_logger("web")

_WEB_PORT = 7865


class WebInterface:
    """
    Wrapper que inicia o FastAPI + Uvicorn em background.
    Recebe referências aos módulos da Keilinks para consultar dados.
    """

    def __init__(self, history_db=None, rag_memory=None, notes=None,
                 stats=None, brain=None, habits=None, study=None):
        self._history_db = history_db
        self._rag        = rag_memory
        self._notes      = notes
        self._stats      = stats
        self._brain      = brain
        self._habits     = habits
        self._study      = study
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Interface web em http://localhost:%d", _WEB_PORT)

    def _run(self):
        try:
            import uvicorn
            app = self._create_app()
            uvicorn.run(app, host="127.0.0.1", port=_WEB_PORT, log_level="warning")
        except ImportError:
            log.warning("uvicorn/fastapi não instalados. Interface web desativada.")
        except Exception as e:
            log.error("Erro ao iniciar web: %s", e)

    def _create_app(self):
        from fastapi import FastAPI, Query
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse, JSONResponse
        from fastapi.middleware.cors import CORSMiddleware

        app = FastAPI(title="Keilinks", docs_url="/api/docs")

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ── API Routes ────────────────────────────────────────────────────────

        @app.get("/api/status")
        def api_status():
            data = {
                "online": True,
                "timestamp": datetime.now().isoformat(),
                "rag_documents": self._rag.count() if self._rag else 0,
                "study_active": self._study.is_active() if self._study else False,
            }
            if self._stats:
                data["hardware"] = {
                    "cpu": self._stats.get_cpu(),
                    "ram": self._stats.get_ram(),
                    "gpu": self._stats.get_gpu(),
                }
            return data

        @app.get("/api/history/search")
        def api_history_search(q: str = Query(..., min_length=1), limit: int = 20):
            if not self._history_db:
                return {"results": []}
            return {"results": self._history_db.search(q, limit=limit)}

        @app.get("/api/history/date/{date}")
        def api_history_date(date: str, limit: int = 50):
            if not self._history_db:
                return {"results": []}
            return {"results": self._history_db.search_by_date(date, limit=limit)}

        @app.get("/api/history/recent")
        def api_history_recent(n: int = 30):
            if not self._history_db:
                return {"messages": []}
            text = self._history_db.get_recent_context(n)
            return {"messages": text}

        @app.get("/api/history/stats")
        def api_history_stats():
            if not self._history_db:
                return {}
            return self._history_db.stats()

        @app.get("/api/rag/search")
        def api_rag_search(q: str = Query(..., min_length=1), n: int = 10):
            if not self._rag:
                return {"results": []}
            return {"results": self._rag.query(q, n_results=n)}

        @app.get("/api/notes")
        def api_notes(limit: int = 20):
            if not self._notes:
                return {"notes": []}
            notes_dir = self._notes._notes_dir
            notes = sorted(notes_dir.glob("*.md"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            items = []
            for n in notes[:limit]:
                items.append({
                    "name":    n.stem,
                    "created": datetime.fromtimestamp(n.stat().st_mtime).isoformat(),
                    "size":    n.stat().st_size,
                })
            return {"notes": items}

        @app.get("/api/notes/{name}")
        def api_note_detail(name: str):
            if not self._notes:
                return {"content": ""}
            return {"content": self._notes.read_note(name)}

        @app.get("/api/hardware")
        def api_hardware():
            if not self._stats:
                return {}
            return {
                "cpu":    self._stats.get_cpu(),
                "ram":    self._stats.get_ram(),
                "gpu":    self._stats.get_gpu(),
                "disk":   self._stats.get_disk(),
            }

        @app.get("/api/study")
        def api_study():
            if not self._study:
                return {"active": False}
            return {
                "active": self._study.is_active(),
                "stats":  self._study.get_stats(),
            }

        @app.get("/api/profile")
        def api_profile():
            if not self._brain or not self._brain.learner:
                return {}
            return {"profile": self._brain.learner.profile}

        @app.get("/api/config")
        def api_config():
            import config
            return {
                k: getattr(config, k)
                for k in dir(config)
                if k.isupper() and not k.startswith("_")
            }

        # ── Serve front-end estático ──────────────────────────────────────────
        dist_dir = Path("web/dist")
        if dist_dir.exists():
            @app.get("/")
            def serve_index():
                return FileResponse(dist_dir / "index.html")

            app.mount("/", StaticFiles(directory=str(dist_dir)), name="static")
        else:
            @app.get("/")
            def serve_fallback():
                return JSONResponse({
                    "message": "Keilinks API online. Front-end não encontrado em web/dist/.",
                    "docs": "/api/docs",
                })

        return app

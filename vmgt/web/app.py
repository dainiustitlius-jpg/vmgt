"""FastAPI servisas: API ir naršyklės puslapiai.

Šis sluoksnis tik tikrina teises ir verčia HTTP į `services` kvietimus –
gamybos taisyklių čia nėra. Taisyklės pažeidimas (`RuleError`) tampa 409 su
žmogui suprantamu tekstu, kurį terminalas parodo tiesiai.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .. import config as cfgmod
from .. import db
from ..services import NotFound, RuleError, analytics, auth, drawings, importer, ncr, projects, seed, tasks

STATIC = Path(__file__).parent / "static"
COOKIE = "vmgt_session"


def create_app(cfg: cfgmod.Config | None = None) -> FastAPI:
    cfg = cfg or cfgmod.load()
    app = FastAPI(title="VMGT", docs_url=None, redoc_url=None)
    app.state.cfg = cfg

    con = db.connect(cfg.db_path)
    db.migrate(con)
    if cfg.seed_sample and seed.is_empty(con):
        seed.seed(con, cfg.files_dir)
    con.close()

    @app.exception_handler(RuleError)
    async def _rule(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(NotFound)
    async def _nf(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    def get_con():
        c = db.connect(cfg.db_path)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def get_user(request: Request, con=Depends(get_con)):
        u = auth.user_by_token(con, request.cookies.get(COOKIE))
        if not u:
            raise HTTPException(401, "Prisijunkite")
        return u

    def need(perm: str):
        def dep(user=Depends(get_user)):
            if perm not in auth.perms_of(user):
                raise HTTPException(403, "Neturite teisės šiam veiksmui")
            return user
        return dep

    # ---------- prisijungimas ----------

    @app.post("/api/login")
    def login(body: dict, response: Response, con=Depends(get_con)):
        token, u = auth.login(con, cfg.session_hours, body.get("login"), body.get("password"), body.get("pin"))
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=cfg.session_hours * 3600)
        return auth.public_user(u)

    @app.post("/api/logout")
    def logout(request: Request, response: Response, con=Depends(get_con)):
        tok = request.cookies.get(COOKIE)
        if tok:
            auth.logout(con, tok)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user=Depends(get_user)):
        return {
            "user": auth.public_user(user),
            "roles": [{"key": k, "label": v[0]} for k, v in auth.ROLES.items()],
            "phase_kinds": [{"key": k, "label": v} for k, v in projects.PHASE_KINDS],
            "project_statuses": [{"key": k, "label": v} for k, v in projects.PROJECT_STATUSES],
            "centre_kinds": [{"key": k, "label": v} for k, v in projects.CENTRE_KINDS],
            "pause_reasons": [{"key": k, "label": v} for k, v in tasks.PAUSE_REASONS],
            "ncr_categories": [{"key": k, "label": v} for k, v in ncr.CATEGORIES],
        }

    # ---------- projektai ----------

    @app.get("/api/projects")
    def project_list(all: int = 0, user=Depends(need("view")), con=Depends(get_con)):
        return projects.list_projects(con, include_done=bool(all))

    @app.post("/api/projects")
    def project_new(body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        return {"id": projects.save_project(con, user["id"], body)}

    @app.get("/api/projects/{pid}")
    def project_get(pid: int, user=Depends(need("view")), con=Depends(get_con)):
        p = projects.get_project(con, pid)
        p["ncr"] = ncr.list_ncr(con, project_id=pid)
        return p

    @app.put("/api/projects/{pid}")
    def project_put(pid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        projects.save_project(con, user["id"], body, pid)
        return {"ok": True}

    @app.post("/api/projects/{pid}/assemblies")
    def asm_new(pid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        return {"id": projects.save_assembly(con, user["id"], pid, body)}

    @app.put("/api/assemblies/{aid}")
    def asm_put(aid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        projects.save_assembly(con, user["id"], None, body, aid)
        return {"ok": True}

    @app.post("/api/projects/{pid}/phases")
    def phase_new(pid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        return {"id": projects.save_phase(con, user["id"], pid, body)}

    @app.put("/api/phases/{phid}")
    def phase_put(phid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        projects.save_phase(con, user["id"], None, body, phid)
        return {"ok": True}

    @app.post("/api/phases/{phid}/status")
    def phase_status(phid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        projects.set_phase_status(con, user["id"], phid, body.get("status"))
        return {"ok": True}

    # ---------- užduotys ----------

    @app.post("/api/tasks")
    def task_new(body: dict, user=Depends(need("tasks")), con=Depends(get_con)):
        return {"id": tasks.create_task(con, user["id"], body)}

    @app.put("/api/tasks/{tid}")
    def task_put(tid: int, body: dict, user=Depends(need("tasks")), con=Depends(get_con)):
        tasks.update_task(con, user["id"], tid, body)
        return {"ok": True}

    @app.delete("/api/tasks/{tid}")
    def task_del(tid: int, user=Depends(need("tasks")), con=Depends(get_con)):
        tasks.delete_task(con, user["id"], tid)
        return {"ok": True}

    @app.post("/api/tasks/{tid}/move")
    def task_move(tid: int, body: dict, user=Depends(need("plan")), con=Depends(get_con)):
        tasks.move(con, user["id"], tid, body.get("where", ""))
        return {"ok": True}

    @app.post("/api/tasks/{tid}/ack_revision")
    def task_ack(tid: int, user=Depends(need("ack_rev")), con=Depends(get_con)):
        tasks.ack_revision(con, user, tid)
        return {"ok": True}

    # ---------- darbo centrai ir eilės ----------

    @app.get("/api/centres")
    def centre_list(all: int = 0, user=Depends(get_user), con=Depends(get_con)):
        out = projects.list_centres(con, active_only=not all)
        return [c for c in out if auth.can_centre(user, c["code"])] if not all else out

    @app.post("/api/centres")
    def centre_new(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"id": projects.save_centre(con, user["id"], body)}

    @app.put("/api/centres/{cid}")
    def centre_put(cid: int, body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        projects.save_centre(con, user["id"], body, cid)
        return {"ok": True}

    @app.get("/api/plan/{code}")
    def plan_get(code: str, user=Depends(need("plan")), con=Depends(get_con)):
        c = projects.centre_by_code(con, code)
        return {"centre": c, "tasks": tasks.plan_view(con, c)}

    @app.post("/api/plan/{code}/approve")
    def plan_approve(code: str, user=Depends(need("plan")), con=Depends(get_con)):
        c = projects.centre_by_code(con, code)
        return {"approved": tasks.approve_queue(con, user["id"], c["id"])}

    # ---------- terminalas ----------

    def _centre_for(con, user, code):
        c = projects.centre_by_code(con, code)
        if not auth.can_centre(user, code):
            raise HTTPException(403, "Šis darbo centras jums nepriskirtas")
        return c

    @app.get("/api/terminal/{code}")
    def terminal(code: str, user=Depends(need("execute")), con=Depends(get_con)):
        return tasks.terminal_view(con, _centre_for(con, user, code))

    @app.post("/api/terminal/{tid}/start")
    def t_start(tid: int, user=Depends(need("execute")), con=Depends(get_con)):
        tasks.start(con, user, tid)
        return {"ok": True}

    @app.post("/api/terminal/{tid}/pause")
    def t_pause(tid: int, body: dict, user=Depends(need("execute")), con=Depends(get_con)):
        tasks.pause(con, user, tid, body.get("reason"), body.get("note", ""))
        return {"ok": True}

    @app.post("/api/terminal/{tid}/resume")
    def t_resume(tid: int, user=Depends(need("execute")), con=Depends(get_con)):
        tasks.resume(con, user, tid)
        return {"ok": True}

    @app.post("/api/terminal/{tid}/stop")
    def t_stop(tid: int, body: dict, user=Depends(need("execute")), con=Depends(get_con)):
        return tasks.stop(con, user, tid, body.get("good", 0), body.get("scrap", 0), body.get("finish"))

    # ---------- cechas ir analitika ----------

    @app.get("/api/floor")
    def floor(user=Depends(need("view")), con=Depends(get_con)):
        return {"now": db.now(), "centres": analytics.floor(con)}

    @app.get("/api/analytics")
    def analytics_get(date_from: str | None = None, date_to: str | None = None,
                      user=Depends(need("view")), con=Depends(get_con)):
        return analytics.report(con, date_from or None, date_to or None)

    # ---------- neatitiktys ----------

    @app.get("/api/ncr")
    def ncr_list(status: str | None = None, user=Depends(need("ncr_report")), con=Depends(get_con)):
        return ncr.list_ncr(con, status=status)

    @app.post("/api/ncr")
    def ncr_new(body: dict, user=Depends(need("ncr_report")), con=Depends(get_con)):
        return {"id": ncr.report(con, user, body)}

    @app.post("/api/ncr/{nid}/assign")
    def ncr_assign(nid: int, body: dict, user=Depends(need("ncr_manage")), con=Depends(get_con)):
        ncr.assign(con, user, nid, body.get("assignee_id"))
        return {"ok": True}

    @app.post("/api/ncr/{nid}/close")
    def ncr_close(nid: int, body: dict, user=Depends(need("ncr_manage")), con=Depends(get_con)):
        ncr.close(con, user, nid, body.get("resolution", ""))
        return {"ok": True}

    # ---------- brėžiniai ir importas ----------

    @app.get("/api/drawings")
    def drawing_list(user=Depends(get_user), con=Depends(get_con)):
        return drawings.list_drawings(con)

    @app.post("/api/drawings")
    async def drawing_new(number: str = Form(...), revision: str = Form(...), title: str = Form(""),
                          file: UploadFile = File(...), user=Depends(need("docs")), con=Depends(get_con)):
        content = await file.read()
        return {"id": drawings.save(con, cfg.files_dir, user, number, revision, file.filename, content, title)}

    @app.get("/api/drawings/{number}/file")
    def drawing_file(number: str, rev: str | None = None, user=Depends(get_user), con=Depends(get_con)):
        path, d = drawings.file_for(con, cfg.files_dir, number, rev)
        if not path.exists():
            raise HTTPException(404, "Failas nerastas diske")
        return FileResponse(path, media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{d["number"]}_rev{d["revision"]}.pdf"'})

    @app.get("/api/import/template")
    def import_template(user=Depends(need("tasks"))):
        return PlainTextResponse(importer.template(), media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="marsrutai.csv"'})

    @app.post("/api/import")
    async def import_routes(file: UploadFile = File(...), dry_run: int = Form(0),
                            user=Depends(need("tasks")), con=Depends(get_con)):
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1257")  # Excel lietuviškoje Windows
        return importer.run(con, user, text, dry_run=bool(dry_run))

    # ---------- vartotojai ----------

    @app.get("/api/users")
    def user_list(user=Depends(need("view")), con=Depends(get_con)):
        return [auth.public_user(u) for u in db.rows(con.execute("SELECT * FROM users ORDER BY name"))]

    @app.post("/api/users")
    def user_new(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"id": auth.create_user(con, body.get("login"), body.get("name") or body.get("login"),
                                       body.get("role"), body.get("password"), body.get("pin") or None,
                                       body.get("centres") or [], by=user["id"])}

    @app.put("/api/users/{uid}")
    def user_put(uid: int, body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        auth.update_user(con, uid, user["id"], **{k: body.get(k) for k in
                                                  ("name", "role", "centres", "password", "pin", "active")})
        return {"ok": True}

    # ---------- puslapiai ----------

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app

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
from ..services import (NotFound, RuleError, actions, analytics, auth, components, drawings, health, importer,
                        meetings, ncr, projects, seed, tasks)

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
    # Nesėkmingų bandymų riba vienam adresui: be jos 4 skaitmenų PIN
    # perrenkamas per kelias minutes. Laikoma atmintyje – perkrovus servisą
    # skaičiavimas prasideda iš naujo, ir to užtenka.
    failed: dict[str, list[float]] = {}
    LIMIT, WINDOW = 8, 300

    @app.post("/api/login")
    def login(body: dict, request: Request, response: Response, con=Depends(get_con)):
        import time

        ip = request.client.host if request.client else "?"
        now = time.monotonic()
        recent = [t for t in failed.get(ip, []) if now - t < WINDOW]
        if len(recent) >= LIMIT:
            raise HTTPException(429, f"Per daug nesėkmingų bandymų. Palaukite {int(WINDOW - (now - recent[0])) // 60 + 1} min.")
        try:
            token, u = auth.login(con, cfg.session_hours, body.get("login"), body.get("password"), body.get("pin"))
        except RuleError:
            failed[ip] = recent + [now]
            raise
        failed.pop(ip, None)
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
            "action_statuses": [{"key": k, "label": v} for k, v in actions.STATUSES],
            "priorities": [{"key": k, "label": v} for k, v in actions.PRIORITIES],
        }

    # ---------- projektai ----------

    @app.get("/api/projects")
    def project_list(all: int = 0, user=Depends(need("view")), con=Depends(get_con)):
        out = projects.list_projects(con, include_done=bool(all))
        for p in out:
            h = health.project_health(con, p["id"])
            p["health"] = {"level": h["level"], "level_label": h["level_label"], "score": h["score"],
                           "dims": {d["key"]: d["level"] for d in h["dimensions"]}}
        return out

    @app.get("/api/projects/{pid}/health")
    def project_health(pid: int, user=Depends(need("view")), con=Depends(get_con)):
        return health.project_health(con, pid)

    @app.post("/api/projects")
    def project_new(body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        return {"id": projects.save_project(con, user["id"], body)}

    @app.get("/api/projects/{pid}")
    def project_get(pid: int, user=Depends(need("view")), con=Depends(get_con)):
        p = projects.get_project(con, pid)
        p["ncr"] = ncr.list_ncr(con, project_id=pid)
        comps = components.list_components(con, project_id=pid)
        p["components"] = comps
        p["components_summary"] = components.summary(comps)
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
        return [c for c in out if auth.can_centre(user, c["code"], c["area_code"])] if not all else out

    @app.post("/api/centres")
    def centre_new(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"id": projects.save_centre(con, user["id"], body)}

    @app.put("/api/centres/{cid}")
    def centre_put(cid: int, body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        projects.save_centre(con, user["id"], body, cid)
        return {"ok": True}

    @app.get("/api/areas")
    def area_list(user=Depends(get_user), con=Depends(get_con)):
        return projects.list_areas(con)

    @app.post("/api/areas")
    def area_new(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"id": projects.save_area(con, user["id"], body)}

    @app.put("/api/areas/{aid}")
    def area_put(aid: int, body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        projects.save_area(con, user["id"], body, aid)
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
        if not auth.can_centre(user, code, c["area_code"]):
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
        return {"now": db.now(), "areas": projects.list_areas(con, active_only=True), "centres": analytics.floor(con)}

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

    # ---------- projekto komandos užduotys ----------

    @app.get("/api/actions")
    def action_list(project_id: int | None = None, owner: str | None = None, status: str | None = None,
                    user=Depends(get_user), con=Depends(get_con)):
        owner_id = user["id"] if owner == "me" else (int(owner) if owner else None)
        if owner_id != user["id"] and "view" not in auth.perms_of(user):
            raise HTTPException(403, "Galite matyti tik savo užduotis")
        return actions.list_actions(con, project_id, owner_id, status or None)

    @app.post("/api/actions")
    def action_new(body: dict, user=Depends(need("actions")), con=Depends(get_con)):
        return {"id": actions.create(con, user["id"], body)}

    @app.get("/api/actions/{aid}")
    def action_get(aid: int, user=Depends(get_user), con=Depends(get_con)):
        x = actions.get(con, aid)
        if x["owner_id"] != user["id"] and "view" not in auth.perms_of(user):
            raise HTTPException(403, "Ne jūsų užduotis")
        x["history"] = actions.history(con, aid)
        x["can_edit"] = actions.can_edit(user, x)
        return x

    @app.put("/api/actions/{aid}")
    def action_put(aid: int, body: dict, user=Depends(get_user), con=Depends(get_con)):
        actions.update(con, user, aid, body)
        return {"ok": True}

    @app.post("/api/actions/{aid}/status")
    def action_status(aid: int, body: dict, user=Depends(get_user), con=Depends(get_con)):
        return actions.set_status(con, user, aid, body.get("status", ""), body.get("reason", ""))

    @app.post("/api/actions/{aid}/comment")
    def action_comment(aid: int, body: dict, user=Depends(get_user), con=Depends(get_con)):
        actions.comment(con, user, aid, body.get("text", ""))
        return {"ok": True}

    # ---------- susitikimų protokolai ----------

    @app.get("/api/meetings")
    def meeting_list(project_id: int | None = None, user=Depends(need("view")), con=Depends(get_con)):
        return meetings.list_meetings(con, project_id)

    @app.post("/api/meetings")
    def meeting_new(body: dict, user=Depends(need("meetings")), con=Depends(get_con)):
        return {"id": meetings.save(con, user, body)}

    @app.get("/api/meetings/{mid}")
    def meeting_get(mid: int, user=Depends(need("view")), con=Depends(get_con)):
        m = meetings.get(con, mid)
        m["text"] = meetings.as_text(m)
        return m

    @app.put("/api/meetings/{mid}")
    def meeting_put(mid: int, body: dict, user=Depends(need("meetings")), con=Depends(get_con)):
        meetings.save(con, user, body, mid)
        return {"ok": True}

    @app.post("/api/meetings/{mid}/approve")
    def meeting_approve(mid: int, user=Depends(need("meetings")), con=Depends(get_con)):
        meetings.approve(con, user, mid)
        return {"ok": True}

    # ---------- komponentų pirkimai ----------

    @app.get("/api/components")
    def comp_list(project_id: int | None = None, status: str | None = None, problems: int = 0,
                  supplier: str | None = None, user=Depends(need("view")), con=Depends(get_con)):
        rows = components.list_components(con, project_id, status or None, bool(problems), supplier or None)
        allrows = components.list_components(con, project_id)
        return {"now": db.now(), "rows": rows, "summary": components.summary(allrows),
                "suppliers": sorted({c["supplier"] for c in allrows if c["supplier"]}),
                "statuses": [{"key": k, "label": v} for k, v in components.STATUSES]}

    @app.get("/api/components/receipts")
    def comp_receipts(limit: int = 30, project_id: int | None = None, user=Depends(need("view")),
                      con=Depends(get_con)):
        return components.receipts(con, min(limit, 200), project_id)

    @app.get("/api/components/template")
    def comp_template(user=Depends(need("purchase"))):
        return PlainTextResponse(components.template(), media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="komponentai.csv"'})

    @app.post("/api/components/import")
    async def comp_import(file: UploadFile = File(...), dry_run: int = Form(0),
                          user=Depends(need("purchase")), con=Depends(get_con)):
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1257")
        return components.import_csv(con, user, text, dry_run=bool(dry_run))

    @app.post("/api/components")
    def comp_new(body: dict, user=Depends(need("purchase")), con=Depends(get_con)):
        return {"id": components.save(con, user["id"], body)}

    @app.put("/api/components/{cid}")
    def comp_put(cid: int, body: dict, user=Depends(need("purchase")), con=Depends(get_con)):
        components.save(con, user["id"], body, cid)
        return {"ok": True}

    @app.post("/api/components/{cid}/receive")
    def comp_receive(cid: int, body: dict, user=Depends(need("receive")), con=Depends(get_con)):
        return components.receive(con, user["id"], cid, body.get("qty"), body.get("note", ""))

    @app.post("/api/components/{cid}/cancel")
    def comp_cancel(cid: int, body: dict, user=Depends(need("purchase")), con=Depends(get_con)):
        components.cancel(con, user["id"], cid, bool(body.get("on", True)))
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

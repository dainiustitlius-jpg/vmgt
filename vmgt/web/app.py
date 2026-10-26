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
from ..services import (NotFound, RuleError, actions, analytics, auth, capacity, components, drawings, health,
                        importer, layout, meetings, ncfiles, ncr, planner, projects, quality, routing, seed,
                        signals, tasks, workcal)
from ..services import home as homepage
from ..services.forecast import forecast

STATIC = Path(__file__).parent / "static"
COOKIE = "vmgt_session"


def create_app(cfg: cfgmod.Config | None = None) -> FastAPI:
    cfg = cfg or cfgmod.load()
    app = FastAPI(title="VMGT", docs_url=None, redoc_url=None)
    app.state.cfg = cfg

    con = db.connect(cfg.db_path)
    db.migrate(con)
    auth.ensure_roles(con)
    con.commit()
    if cfg.seed_sample and seed.is_empty(con):
        seed.seed(con, cfg.files_dir, nc_dir=cfg.nc_path, demo_projects=cfg.seed_demo)
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
        return auth.public_user(auth.load_perms(con, u))

    @app.post("/api/logout")
    def logout(request: Request, response: Response, con=Depends(get_con)):
        tok = request.cookies.get(COOKIE)
        if tok:
            auth.logout(con, tok)
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user=Depends(get_user), con=Depends(get_con)):
        return {
            "user": auth.public_user(user),
            "roles": [{"key": r["code"], "label": r["name"]} for r in auth.list_roles(con)],
            "perm_modules": [{"key": k, "label": l, "perms": [{"key": p, "label": pl, "description": auth.PERMS[p],
                                                               "scoped": p in auth.SCOPED} for p, pl in ps]}
                             for k, l, ps in auth.MODULES],
            "phase_kinds": [{"key": k, "label": v} for k, v in projects.PHASE_KINDS],
            "project_statuses": [{"key": k, "label": v} for k, v in projects.PROJECT_STATUSES],
            "centre_kinds": [{"key": k, "label": v} for k, v in projects.CENTRE_KINDS],
            "pause_reasons": [{"key": k, "label": v} for k, v in tasks.PAUSE_REASONS],
            "ncr_categories": [{"key": k, "label": v} for k, v in ncr.CATEGORIES],
            "action_statuses": [{"key": k, "label": v} for k, v in actions.STATUSES],
            "priorities": [{"key": k, "label": v} for k, v in actions.PRIORITIES],
            # kaip technologo failų katalogą mato cecho kompiuteriai
            "nc_share": cfg.nc_share or str(cfg.nc_path.resolve()),
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
        # operacijų prognozė pagal centrų eiles ir darbo kalendorių
        fc = forecast(con)
        for t in p["tasks"]:
            t["forecast"] = fc.get(t["id"])
        return p

    @app.put("/api/projects/{pid}")
    def project_put(pid: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        # prioritetas ir patvirtinimas iš krepšelio – per planuotoją: poveikis kitiems projektams ir pranešimai
        body = dict(body)
        cur = projects.get_project(con, pid)
        if body.get("status") == "vykdomas" and cur["status"] == "krepselis":
            planner.apply(con, user, {"kind": "activate", "project_id": pid})
            body.pop("status")
        if "priority" in body and int(body["priority"] or 0) != cur["priority"]:
            planner.apply(con, user, {"kind": "priority", "project_id": pid, "priority": int(body.pop("priority"))})
        body.pop("priority", None)
        if body:
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
        body = dict(body)
        ph = db.row(con.execute("SELECT plan_start, plan_end FROM phases WHERE id=?", (phid,)))
        if ph and ("plan_start" in body or "plan_end" in body):
            a, b = body.pop("plan_start", ph["plan_start"]), body.pop("plan_end", ph["plan_end"])
            if a and b and (a, b) != (ph["plan_start"], ph["plan_end"]):
                planner.apply(con, user, {"kind": "phase", "phase_id": phid, "plan_start": a, "plan_end": b})
            elif (a, b) != (ph["plan_start"], ph["plan_end"]):
                body.update({"plan_start": a, "plan_end": b})      # dar be vienos datos – poveikio nėra ką skaičiuoti
        if body:
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
        imp = planner.apply(con, user, {"kind": "queue", "task_id": tid, "where": body.get("where", "")})
        return {"ok": True, "affected": imp["affected"]}

    @app.post("/api/tasks/{tid}/ack_revision")
    def task_ack(tid: int, user=Depends(need("ack_rev")), con=Depends(get_con)):
        tasks.ack_revision(con, user, tid)
        return {"ok": True}

    # ---------- darbo centrai ir eilės ----------

    @app.get("/api/centres")
    def centre_list(all: int = 0, user=Depends(get_user), con=Depends(get_con)):
        out = projects.list_centres(con, active_only=not all)
        # kas mato cechą (`view`) – mato visus centrus; operatorius – tik savo
        if all or "view" in auth.perms_of(user):
            return out
        return [c for c in out if auth.can_centre(user, c["code"], c["area_code"])]

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

    # ---------- darbo kalendorius ----------

    @app.get("/api/calendar")
    def cal_year(scope: str = "factory", id: int = 0, year: int = 0, user=Depends(need("view")),
                 con=Depends(get_con)):
        return workcal.year_view(con, scope, id, year or int(db.now()[:4]))

    def cal_scope(con, user, scope, sid):
        """Meistras (rolė „savo baruose“) keičia tik savo barų ir centrų
        kalendorių; gamyklos kalendorius ir bendri šablonai – ne jo."""
        if auth.scope_of(user) == "all":
            return
        if scope == "area":
            r = con.execute("SELECT code FROM areas WHERE id=?", (int(sid or 0),)).fetchone()
            if r and auth.can_centre(user, "", r[0]):
                return
        elif scope == "centre":
            r = con.execute("SELECT c.code, ar.code FROM work_centres c LEFT JOIN areas ar ON ar.id=c.area_id "
                            "WHERE c.id=?", (int(sid or 0),)).fetchone()
            if r and auth.can_centre(user, r[0], r[1]):
                return
        raise RuleError("Galite keisti tik savo barų ir jų centrų kalendorių" if scope != "factory" else
                        "Gamyklos kalendorių ir pamainų šablonus keičia planuotojas ar vadovas – jūs – savo barų")

    @app.get("/api/calendar/patterns")
    def cal_patterns(user=Depends(need("view")), con=Depends(get_con)):
        return workcal.list_patterns(con)

    @app.post("/api/calendar/patterns")
    def cal_pattern_new(body: dict, user=Depends(need("calendar")), con=Depends(get_con)):
        cal_scope(con, user, "factory", 0)
        return {"id": workcal.save_pattern(con, user["id"], body)}

    @app.put("/api/calendar/patterns/{pid}")
    def cal_pattern_put(pid: int, body: dict, user=Depends(need("calendar")), con=Depends(get_con)):
        cal_scope(con, user, "factory", 0)
        # šablono pakeitimas keičia visų jį naudojančių darbo laiką – su poveikiu
        def do():
            workcal.save_pattern(con, user["id"], body, pid)
            return {"summary": f"Pamainų šablonas „{body.get('name', '')}“ pakeistas"}
        return planner.calendar_change(con, user, do, body.get("note", ""))

    @app.put("/api/calendar/pattern")
    def cal_set_pattern(body: dict, user=Depends(need("calendar")), con=Depends(get_con)):
        cal_scope(con, user, body.get("scope"), body.get("scope_id"))
        def do():
            workcal.set_pattern(con, user["id"], body.get("scope"), body.get("scope_id"), body.get("pattern_id"))
            v = workcal.year_view(con, body.get("scope"), body.get("scope_id"), int(db.now()[:4]))
            return {"summary": f"{v['name']}: pamainos – {v['pattern']['name'] if v['pattern'] else '—'}"
                               f"{'' if body.get('pattern_id') else ' (paveldėta)'}"}
        return planner.calendar_change(con, user, do, body.get("note", ""))

    @app.post("/api/calendar/days")
    def cal_days(body: dict, user=Depends(need("calendar")), con=Depends(get_con)):
        cal_scope(con, user, body.get("scope"), body.get("scope_id"))
        return planner.calendar_change(con, user, lambda: workcal.set_days(con, user["id"], body), body.get("note", ""))

    # ---------- planuotojo Gantt, poveikis, signalai ----------

    @app.get("/api/planner")
    def planner_board(weeks: int = 12, basket: int = 1, user=Depends(need("view")), con=Depends(get_con)):
        return planner.board(con, max(4, min(weeks, 40)), bool(basket))

    def need_planning(user=Depends(get_user)):
        # planuotojas datų keisti per projekto kortelę negali (`projects`), bet plane – taip
        if not auth.perms_of(user) & {"plan", "projects"}:
            raise HTTPException(403, "Neturite teisės šiam veiksmui")
        return user

    @app.post("/api/planner/impact")
    def planner_impact(body: dict, user=Depends(need_planning), con=Depends(get_con)):
        return planner.impact(con, user, body)

    @app.post("/api/planner/apply")
    def planner_apply(body: dict, user=Depends(need_planning), con=Depends(get_con)):
        note = body.pop("note", "")
        return planner.apply(con, user, body, note)

    @app.get("/api/planner/changes")
    def planner_changes(project_id: int | None = None, limit: int = 40, user=Depends(need("view")),
                        con=Depends(get_con)):
        return signals.changes(con, min(limit, 200), project_id)

    @app.get("/api/notifications")
    def notif_list(unread: int = 0, user=Depends(get_user), con=Depends(get_con)):
        signals.scan(con)                    # pažadėtos datos praėjo – signalas be fono gijų
        return {"unread": signals.unread(con, user["id"]), "items": signals.list_for(con, user["id"], bool(unread))}

    @app.get("/api/notifications/count")
    def notif_count(user=Depends(get_user), con=Depends(get_con)):
        signals.scan(con)
        return {"unread": signals.unread(con, user["id"])}

    @app.post("/api/notifications/read")
    def notif_read(body: dict, user=Depends(get_user), con=Depends(get_con)):
        return {"read": signals.mark_read(con, user["id"], body.get("ids"))}

    @app.get("/api/plan/{code}")
    def plan_get(code: str, user=Depends(need("plan")), con=Depends(get_con)):
        c = projects.centre_by_code(con, code)
        return {"centre": c, "tasks": tasks.plan_view(con, c)}

    @app.post("/api/plan/{code}/approve")
    def plan_approve(code: str, user=Depends(need("plan")), con=Depends(get_con)):
        c = projects.centre_by_code(con, code)
        auth.require_at(user, "plan", c["code"], c["area_code"])
        return {"approved": tasks.approve_queue(con, user["id"], c["id"])}

    # ---------- terminalas ----------

    def _centre_for(con, user, code):
        c = projects.centre_by_code(con, code)
        if not auth.can_centre(user, code, c["area_code"]):
            raise HTTPException(403, "Šis darbo centras jums nepriskirtas")
        return c

    @app.get("/api/terminal/{code}")
    def terminal(code: str, user=Depends(need("execute")), con=Depends(get_con)):
        return tasks.terminal_view(con, _centre_for(con, user, code), user)

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

    # ---------- technologinis srautas ir atsekamumas ----------

    def view_or_execute(user=Depends(get_user)):
        # maršruto lapo QR nuskenuoja ir operatorius, kuris projektų nemato
        if not auth.perms_of(user) & {"view", "execute"}:
            raise HTTPException(403, "Neturite teisės šiam veiksmui")
        return user

    @app.get("/api/route/{aid}")
    def route_get(aid: int, user=Depends(view_or_execute), con=Depends(get_con)):
        return routing.trace(con, aid)

    @app.post("/api/route/{aid}/release")
    def route_release(aid: int, user=Depends(need("release")), con=Depends(get_con)):
        return routing.release(con, user["id"], aid)

    @app.post("/api/route/{aid}/unrelease")
    def route_unrelease(aid: int, body: dict, user=Depends(need("release")), con=Depends(get_con)):
        routing.unrelease(con, user["id"], aid, body.get("reason", ""))
        return {"ok": True}

    # ---------- technologo failai ir darbo aplinka ----------

    @app.post("/api/tasks/{tid}/files")
    async def file_upload(tid: int, file: UploadFile = File(...), note: str = Form(""),
                          user=Depends(need("tasks")), con=Depends(get_con)):
        content = await file.read()
        return ncfiles.save(con, cfg.nc_path, user, tid, file.filename, content, note)

    @app.get("/api/tasks/{tid}/files")
    def file_list(tid: int, history: int = 0, user=Depends(view_or_execute), con=Depends(get_con)):
        return ncfiles.list_for(con, [tid], history=bool(history))[tid]

    @app.get("/api/files/{fid}")
    def file_get(fid: int, user=Depends(view_or_execute), con=Depends(get_con)):
        f = ncfiles.get(con, fid)
        path = ncfiles.full_path(cfg.nc_path, f)
        if not path.exists():
            raise HTTPException(404, "Failas nerastas diske")
        # visada atsisiųsti, ne atidaryti naršyklėje – tai staklių failai
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    @app.delete("/api/files/{fid}")
    def file_remove(fid: int, user=Depends(need("tasks")), con=Depends(get_con)):
        ncfiles.remove(con, user, fid)
        return {"ok": True}

    @app.post("/api/tasks/{tid}/ack_files")
    def file_ack(tid: int, user=Depends(need("ack_rev")), con=Depends(get_con)):
        return {"acked": ncfiles.ack(con, user, tid)}

    @app.get("/api/tech/worklist")
    def tech_worklist(mine: int = 0, user=Depends(need("tasks")), con=Depends(get_con)):
        return routing.worklist(con, user["id"] if mine else None)

    @app.get("/api/tech/sources")
    def tech_sources(user=Depends(need("tasks")), con=Depends(get_con)):
        # mazgai su maršrutu – iš jų galima kopijuoti
        return db.rows(con.execute(
            "SELECT a.id, a.code, a.name, a.qty, p.code AS project_code, COUNT(t.id) AS ops "
            "FROM assemblies a JOIN projects p ON p.id=a.project_id JOIN tasks t ON t.assembly_id=a.id "
            "GROUP BY a.id ORDER BY p.code DESC, a.sort"))

    @app.post("/api/route/{aid}/copy")
    def route_copy(aid: int, body: dict, user=Depends(need("tasks")), con=Depends(get_con)):
        return routing.copy_route(con, cfg.nc_path, user, int(body.get("from_assembly") or 0), aid,
                                  bool(body.get("files", True)))

    @app.get("/api/qr")
    def qr(data: str, user=Depends(get_user)):
        # QR piešiamas serveryje: cecho kompiuteriai gali būti be interneto
        import io

        import segno

        buf = io.BytesIO()
        segno.make(data, error="m").save(buf, kind="svg", scale=4, border=2, xmldecl=False)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    # ---------- cechas ir analitika ----------

    @app.get("/api/floor")
    def floor(user=Depends(need("view")), con=Depends(get_con)):
        return {"now": db.now(), "areas": projects.list_areas(con, active_only=True), "centres": analytics.floor(con)}

    @app.get("/api/floor/plan")
    def floor_plan(project_id: int | None = None, user=Depends(need("view")), con=Depends(get_con)):
        return layout.plan(con, project_id)

    @app.put("/api/floor/layout")
    def floor_layout(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        layout.save(con, user["id"], body)
        return {"ok": True}

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
        # 8D: uždarant – šakninė priežastis ir sprendimas dėl gaminio privalomi
        quality.update_ncr(con, user, nid, {k: body[k] for k in ("containment", "root_cause", "corrective",
                                                                 "preventive", "disposition") if k in body})
        n = db.row(con.execute("SELECT root_cause, disposition FROM ncr WHERE id=?", (nid,)))
        if not n or not n["root_cause"] or not n["disposition"]:
            raise HTTPException(409, "Uždarant nurodykite šakninę priežastį ir sprendimą dėl gaminio")
        ncr.close(con, user, nid, body.get("resolution", ""))
        return {"ok": True}

    @app.get("/api/ncr/{nid}")
    def ncr_get(nid: int, user=Depends(need("ncr_report")), con=Depends(get_con)):
        n = db.row(con.execute("SELECT id FROM ncr WHERE id=?", (nid,)))
        if not n:
            raise HTTPException(404, "Neatitikties nėra")
        x = next(r for r in ncr.list_ncr(con) if r["id"] == nid)
        x["files"] = quality.ncr_files(con, nid)
        x["disposition_label"] = quality.DISPOSITION_LABEL.get(x.get("disposition") or "", "")
        return x

    @app.put("/api/ncr/{nid}")
    def ncr_put(nid: int, body: dict, user=Depends(need("ncr_manage")), con=Depends(get_con)):
        quality.update_ncr(con, user, nid, body)
        return {"ok": True}

    @app.post("/api/ncr/{nid}/files")
    async def ncr_file_up(nid: int, file: UploadFile = File(...), user=Depends(need("ncr_report")),
                          con=Depends(get_con)):
        return {"id": quality.add_ncr_file(con, cfg.files_dir, user, nid, file.filename or "foto.jpg", await file.read())}

    @app.get("/api/ncr_files/{fid}")
    def ncr_file_get(fid: int, user=Depends(need("ncr_report")), con=Depends(get_con)):
        f = db.row(con.execute("SELECT * FROM ncr_files WHERE id=?", (fid,)))
        if not f:
            raise HTTPException(404, "Failo nėra")
        return FileResponse(quality.stored_path(cfg.files_dir, f["stored"]), filename=f["name"])

    # ---------- kokybė: patikros, medžiagos, suvirinimas, dosjė ----------

    def any_perm(*ps):
        def dep(user=Depends(get_user)):
            if not auth.perms_of(user) & set(ps):
                raise HTTPException(403, "Neturite teisės šiam veiksmui")
            return user
        return dep

    @app.get("/api/quality/meta")
    def q_meta(user=Depends(get_user), con=Depends(get_con)):
        return {"exc_classes": quality.EXC_CLASSES, "performers": [{"key": k, "label": v} for k, v in quality.PERFORMERS],
                "dispositions": [{"key": k, "label": v} for k, v in quality.DISPOSITIONS],
                "cert_types": quality.CERT_TYPES, "templates": quality.list_templates(con), "wps": quality.list_wps(con)}

    @app.get("/api/quality/templates")
    def q_templates(all: int = 0, user=Depends(any_perm("tasks", "quality")), con=Depends(get_con)):
        return quality.list_templates(con, not all)

    @app.post("/api/quality/templates")
    def q_template_new(body: dict, user=Depends(any_perm("tasks", "quality")), con=Depends(get_con)):
        return {"id": quality.save_template(con, user["id"], body)}

    @app.put("/api/quality/templates/{tid}")
    def q_template_put(tid: int, body: dict, user=Depends(any_perm("tasks", "quality")), con=Depends(get_con)):
        return {"id": quality.save_template(con, user["id"], body, tid)}

    @app.post("/api/tasks/{tid}/checks")
    def q_check_add(tid: int, body: dict, user=Depends(any_perm("tasks", "quality")), con=Depends(get_con)):
        return {"id": quality.add_check(con, user["id"], tid, body)}

    @app.delete("/api/checks/{cid}")
    def q_check_del(cid: int, user=Depends(any_perm("tasks", "quality")), con=Depends(get_con)):
        quality.remove_check(con, user["id"], cid)
        return {"ok": True}

    @app.post("/api/checks/{cid}/result")
    def q_check_result(cid: int, body: dict, user=Depends(any_perm("execute", "quality")), con=Depends(get_con)):
        return quality.record(con, user, cid, body.get("ok"), body.get("value"), body.get("note", ""))

    @app.post("/api/checks/{cid}/waive")
    def q_check_waive(cid: int, body: dict, user=Depends(any_perm("quality", "ack_rev")), con=Depends(get_con)):
        return quality.waive(con, user, cid, body.get("reason", ""))

    @app.get("/api/checks/{cid}/history")
    def q_check_hist(cid: int, user=Depends(get_user), con=Depends(get_con)):
        return db.rows(con.execute("SELECT r.*, u.name AS user_name FROM check_results r LEFT JOIN users u "
                                   "ON u.id=r.user_id WHERE r.check_id=? ORDER BY r.at", (cid,)))

    @app.get("/api/quality/queue")
    def q_queue(user=Depends(need("quality")), con=Depends(get_con)):
        return quality.qc_queue(con)

    @app.get("/api/quality/lots")
    def q_lots(q: str = "", ok: int = 0, user=Depends(any_perm("view", "execute")), con=Depends(get_con)):
        return quality.list_lots(con, q, bool(ok))

    @app.post("/api/quality/lots")
    async def q_lot_new(heat_no: str = Form(...), material: str = Form(...), product: str = Form(""),
                        supplier: str = Form(""), cert_no: str = Form(""), cert_type: str = Form("3.1"),
                        qty: float = Form(0), unit: str = Form("vnt"), note: str = Form(""),
                        file: UploadFile | None = File(None), user=Depends(any_perm("quality", "receive")),
                        con=Depends(get_con)):
        data = {"heat_no": heat_no, "material": material, "product": product, "supplier": supplier,
                "cert_no": cert_no, "cert_type": cert_type, "qty": qty, "unit": unit, "note": note}
        content = await file.read() if file else None
        return {"id": quality.save_lot(con, cfg.files_dir, user, data, content or None, file.filename if file else "")}

    @app.post("/api/quality/lots/{lid}/status")
    def q_lot_status(lid: int, body: dict, user=Depends(need("quality")), con=Depends(get_con)):
        quality.set_lot_status(con, user, lid, body.get("status"), body.get("note", ""))
        return {"ok": True}

    @app.get("/api/quality/lots/{lid}/cert")
    def q_lot_cert(lid: int, user=Depends(any_perm("view", "execute")), con=Depends(get_con)):
        lot = db.row(con.execute("SELECT * FROM material_lots WHERE id=?", (lid,)))
        if not lot or not lot["cert_file"]:
            raise HTTPException(404, "Sertifikato nėra")
        return FileResponse(quality.stored_path(cfg.files_dir, lot["cert_file"]), media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{lot["heat_no"]}.pdf"'})

    @app.post("/api/tasks/{tid}/materials")
    def q_use_lot(tid: int, body: dict, user=Depends(any_perm("execute", "quality")), con=Depends(get_con)):
        return {"id": quality.use_lot(con, user, tid, int(body.get("lot_id") or 0), body.get("qty") or 1)}

    @app.get("/api/quality/wps")
    def q_wps(user=Depends(get_user), con=Depends(get_con)):
        return quality.list_wps(con, active_only=False)

    @app.post("/api/quality/wps")
    async def q_wps_new(code: str = Form(...), process: str = Form(...), material_group: str = Form(...),
                        description: str = Form(""), file: UploadFile | None = File(None),
                        user=Depends(need("quality")), con=Depends(get_con)):
        content = await file.read() if file else None
        return {"id": quality.save_wps(con, cfg.files_dir, user["id"], {"code": code, "process": process,
                                       "material_group": material_group, "description": description}, content or None)}

    @app.get("/api/quality/qualifications")
    def q_quals(user=Depends(any_perm("view", "quality")), con=Depends(get_con)):
        return quality.list_qualifications(con)

    @app.post("/api/quality/qualifications")
    async def q_qual_new(user_id: int = Form(...), process: str = Form(...), material_group: str = Form(...),
                         valid_until: str = Form(...), standard: str = Form("ISO 9606-1"), cert_no: str = Form(""),
                         note: str = Form(""), file: UploadFile | None = File(None), user=Depends(need("quality")),
                         con=Depends(get_con)):
        content = await file.read() if file else None
        return {"id": quality.save_qualification(con, cfg.files_dir, user["id"], {
            "user_id": user_id, "process": process, "material_group": material_group, "valid_until": valid_until,
            "standard": standard, "cert_no": cert_no, "note": note}, content or None)}

    @app.put("/api/quality/qualifications/{qid}")
    def q_qual_put(qid: int, body: dict, user=Depends(need("quality")), con=Depends(get_con)):
        return {"id": quality.save_qualification(con, cfg.files_dir, user["id"], body, None, qid)}

    @app.get("/api/quality/file")
    def q_file(path: str, user=Depends(any_perm("view", "quality")), con=Depends(get_con)):
        # tik WPS ir kvalifikacijų failai – kelias tikrinamas, kad neišeitų iš katalogo
        if not path.startswith(("wps/", "kvalifikacijos/")):
            raise HTTPException(404, "Failo nėra")
        return FileResponse(quality.stored_path(cfg.files_dir, path))

    @app.get("/api/quality/dossier/{pid}")
    def q_dossier(pid: int, user=Depends(need("view")), con=Depends(get_con)):
        return quality.dossier(con, pid)

    @app.get("/api/quality/dossier/{pid}/zip")
    def q_dossier_zip(pid: int, user=Depends(need("view")), con=Depends(get_con)):
        code = db.row(con.execute("SELECT code FROM projects WHERE id=?", (pid,)))
        if not code:
            raise HTTPException(404, "Projekto nėra")
        return Response(quality.dossier_zip(con, cfg.files_dir, pid), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{code["code"]}_kokybes_dosje.zip"'})

    # ---------- resursų apkrova ----------

    @app.get("/api/capacity")
    def capacity_report(weeks: int = 12, basket: int = 1, user=Depends(need("view")), con=Depends(get_con)):
        return capacity.report(con, max(4, min(weeks, 52)), bool(basket))

    @app.get("/api/departments")
    def dept_list(user=Depends(need("view")), con=Depends(get_con)):
        return capacity.list_departments(con)

    @app.post("/api/departments")
    def dept_new(body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        return {"id": capacity.save_department(con, user["id"], body)}

    @app.put("/api/departments/{did}")
    def dept_put(did: int, body: dict, user=Depends(need("projects")), con=Depends(get_con)):
        capacity.save_department(con, user["id"], body, did)
        return {"ok": True}

    # ---------- projekto komandos užduotys ----------

    @app.get("/api/actions")
    def action_list(project_id: int | None = None, owner: str | None = None, status: str | None = None,
                    user=Depends(get_user), con=Depends(get_con)):
        owner_id = user["id"] if owner == "me" else (int(owner) if owner else None)
        if owner_id != user["id"] and "view" not in auth.perms_of(user):
            raise HTTPException(403, "Galite matyti tik savo užduotis")
        return actions.list_actions(con, project_id, owner_id, status or None, viewer_id=user["id"])

    @app.post("/api/actions")
    def action_new(body: dict, user=Depends(get_user), con=Depends(get_con)):
        # asmeninę užduotį sau kuria kiekvienas, projekto – teisė `actions`
        if body.get("project_id") and "actions" not in auth.perms_of(user):
            raise HTTPException(403, "Projekto užduotis kuria projekto vadovas ir komanda")
        return {"id": actions.create(con, user["id"], body)}

    @app.get("/api/my/week")
    def my_week(start: str | None = None, user=Depends(get_user), con=Depends(get_con)):
        from datetime import date

        try:
            d = date.fromisoformat(start) if start else None
        except ValueError:
            raise HTTPException(400, "Neteisinga data") from None
        return actions.week(con, user["id"], d)

    @app.get("/api/actions/{aid}")
    def action_get(aid: int, user=Depends(get_user), con=Depends(get_con)):
        x = actions.get(con, aid)
        if not actions.can_see(user, x):
            # svetima asmeninė užduotis – lyg jos nebūtų
            raise HTTPException(404 if x["personal"] else 403, "Užduoties nėra" if x["personal"] else "Ne jūsų užduotis")
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
        return [auth.public_user(auth.load_perms(con, u)) for u in db.rows(con.execute("SELECT * FROM users ORDER BY name"))]

    @app.get("/api/users/{uid}")
    def user_get(uid: int, user=Depends(need("admin")), con=Depends(get_con)):
        u = db.row(con.execute("SELECT * FROM users WHERE id=?", (uid,)))
        if not u:
            raise NotFound("Vartotojo nėra")
        last = con.execute("SELECT MAX(at) FROM events WHERE entity='user' AND entity_id=? AND action='login'",
                           (uid,)).fetchone()[0]
        return {**auth.public_user(auth.load_perms(con, u)), "modules": auth.describe(con, u), "last_login": last,
                "log": auth.access_log(con, "user", uid, 50)}

    @app.get("/api/roles")
    def role_list(user=Depends(need("admin")), con=Depends(get_con)):
        return auth.list_roles(con)

    @app.post("/api/roles")
    def role_new(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"code": auth.save_role(con, user["id"], body.get("code"), body, new=True)}

    @app.put("/api/roles/{code}")
    def role_put(code: str, body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"code": auth.save_role(con, user["id"], code, body)}

    @app.delete("/api/roles/{code}")
    def role_del(code: str, user=Depends(need("admin")), con=Depends(get_con)):
        auth.delete_role(con, user["id"], code)
        return {"ok": True}

    @app.get("/api/access_log")
    def access_log(target: str | None = None, id: str | None = None, user=Depends(need("admin")),
                   con=Depends(get_con)):
        return auth.access_log(con, target, id, 300)

    @app.get("/api/home")
    def home(user=Depends(get_user), con=Depends(get_con)):
        return homepage.tiles(con, user)

    @app.post("/api/users")
    def user_new(body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        return {"id": auth.create_user(con, body.get("login"), body.get("name") or body.get("login"),
                                       body.get("role"), body.get("password"), body.get("pin") or None,
                                       body.get("centres") or [], by=user["id"])}

    @app.put("/api/users/{uid}")
    def user_put(uid: int, body: dict, user=Depends(need("admin")), con=Depends(get_con)):
        auth.update_user(con, uid, user["id"], **{k: body.get(k) for k in
                                                  ("name", "role", "centres", "password", "pin", "active",
                                                   "perm_add", "perm_remove")})
        return {"ok": True}

    # ---------- puslapiai ----------

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app

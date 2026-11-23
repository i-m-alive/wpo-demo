# ==========
# stub-sap
# ==========

PRODUCTION_PLAN = {
    "as_of": "2026-11-20T01:00:00Z",
    "sites": [
        {"site_id": f"S{i:02d}", "line_id": f"S{i:02d}-L1",
         "shift": "EARLY", "planned_units": 4200, "headcount_required": 5}
        for i in range(1, 15)
    ]
}
# GET /production_plan  -> PRODUCTION_PLAN

SHIFT_CONFIRM_OK = {"status": "ok", "confirmed": 14}
# POST /shift_confirm  -> SHIFT_CONFIRM_OK


# ==========
# stub-workday
# ==========

ABSENCES = {
    "as_of": "2026-11-20T01:00:00Z",
    "absences": [
        {"worker_id": "W03", "site_id": "S01", "date": "2026-11-20", "reason": "LEAVE"},
        {"worker_id": "W07", "site_id": "S04", "date": "2026-11-20", "reason": "SICK"},
    ]
}
# GET /absences  -> ABSENCES

WORKERS = {
    "as_of": "2026-11-20T01:00:00Z",
    "workers": [
        {"worker_id": f"W{i:02d}", "site_id": f"S{((i - 1) % 14) + 1:02d}",
         "contract_hours": 37.5, "skills": ["PKG"]}
        for i in range(1, 11)
    ]
}
# GET /workers  -> WORKERS

SCHEDULES_OK = {"status": "ok", "published": 14}
# POST /schedules  -> SCHEDULES_OK

THROTTLED = {"error": "TOO_MANY_REQUESTS",
             "message": "Tenant request limit exceeded"}
# returned with HTTP 429 and header Retry-After: <30|60|120>


# ==========
# stub-mes
# ==========

LINE_AVAILABILITY = {
    "as_of": "2026-11-20T01:00:00Z",
    "lines": [
        {"line_id": f"S{i:02d}-L1", "status": "RUNNING", "maintenance_window": None}
        for i in range(1, 15)
    ]
}
# GET /line_availability  -> LINE_AVAILABILITY

LINE_AVAILABILITY_EMPTY = {"as_of": "2026-11-20T01:00:00Z", "lines": []}
# returned with HTTP 200 when the empty-result mode is on


# ==========
# stub-lms
# ==========

TRAINING_CURRENCY = {
    "as_of": "2026-11-20T01:00:00Z",
    "qualifications": [
        {"worker_id": f"W{i:02d}", "qualification_code": "PKG",
         "status": "CURRENT", "expires_on": "2027-06-30"}
        for i in range(1, 11)
    ]
}
# GET /training_currency  -> TRAINING_CURRENCY

TRAINING_CURRENCY_EMPTY = {"as_of": "2026-11-20T01:00:00Z", "qualifications": []}


# ==========
# stub-cuopt
# ==========

SOLVE_OK = {
    "status": "OK",
    "solver_time_ms": 1800,
    "solver_cost": 0.42,
    "roster": [
        {"site_id": f"S{i:02d}", "line_id": f"S{i:02d}-L1", "shift": "EARLY",
         "assigned": ["W01", "W02", "W03", "W04", "W05"]}
        for i in range(1, 15)
    ]
}
# POST /solve  -> SOLVE_OK

SOLVE_INFEASIBLE = {"status": "INFEASIBLE", "solver_time_ms": 2400,
                    "solver_cost": 0.55, "roster": []}
# also HTTP 200 - a solver refusing is not an HTTP error


# ==========
# stub-teams
# ==========

NOTIFY_ACCEPTED = {"status": "accepted", "message_id": "msg-0001"}
# POST /notify  -> HTTP 202 with NOTIFY_ACCEPTED


# ==========
# stub-policy
# ==========

POLICY_RULES = {
    "as_of": "2026-11-20T01:00:00Z",
    "rules": [
        {"rule_id": "R01", "type": "MAX_CONSECUTIVE_DAYS", "value": 6},
        {"rule_id": "R02", "type": "MIN_REST_HOURS", "value": 11},
        {"rule_id": "R03", "type": "MAX_HOURS_PER_WEEK", "value": 48},
        {"rule_id": "R04", "type": "SKILL_REQUIRED", "value": True},
    ]
}
# GET /rules  -> POLICY_RULES

POLICY_RULES_EMPTY = {"as_of": "2026-11-20T01:00:00Z", "rules": []}
# returned with HTTP 200 when the empty-result mode is on


# ==========
# stub-roster-store
# ==========

ROSTER_STORE_OK = {"status": "ok", "roster_id": "R-2026-11-20", "sites_written": 14}
# POST /roster  -> ROSTER_STORE_OK

ROSTER_STORE_GET = {
    "roster_id": "R-2026-11-20",
    "generated_at": "2026-11-20T03:58:00Z",
    "status": "PUBLISHED",
    "sites": [
        {"site_id": f"S{i:02d}", "line_id": f"S{i:02d}-L1", "shift": "EARLY",
         "assigned": ["W01", "W02", "W03", "W04", "W05"]}
        for i in range(1, 15)
    ]
}
# GET /roster  -> ROSTER_STORE_GET


# ==========
# stub-llm   (stands in for Azure OpenAI - no API key needed)
# ==========

CHAT_COMPLETION = {
    "id": "chatcmpl-0001",
    "model": "gpt-4o-mini",
    "choices": [
        {"index": 0, "finish_reason": "stop",
         "message": {"role": "assistant", "content": "{\"ok\": true}"}}
    ],
    "usage": {"prompt_tokens": 820, "completion_tokens": 140, "total_tokens": 960}
}
# POST /chat/completions  -> CHAT_COMPLETION

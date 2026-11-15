"""Scenario A (organization) and Scenario B (engineer): the complete Model A project workflow."""
from tests.conftest import PDF, Client, future, invite_member, new_project, proposal_body, register


def _to_in_progress(w, price=400000):
    owner, eng = w["owner"], w["eng"]
    p = new_project(owner)
    owner.ok("POST", f"/projects/{p['id']}/publish")
    prop = eng.ok("POST", f"/projects/{p['id']}/proposals", json=proposal_body(price))
    owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "applications_closed"})
    owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "under_evaluation"})
    owner.ok("POST", f"/proposals/{prop['id']}/accept")
    eng.ok("POST", f"/projects/{p['id']}/agreement/accept")
    owner.ok("POST", f"/projects/{p['id']}/start")
    return p, prop


def test_full_project_lifecycle(world):
    owner, eng, eng2, admin = world["owner"], world["eng"], world["eng2"], world["admin"]
    # 1-3: organization creates and publishes a project
    p = new_project(owner)
    assert p["status"] == "draft"
    assert eng.call("GET", f"/projects/{p['id']}").status_code == 404          # drafts are private
    assert owner.ok("POST", f"/projects/{p['id']}/publish")["status"] == "published"
    market = eng.ok("GET", "/projects?scope=marketplace")["data"]
    assert [x["id"] for x in market] == [p["id"]]

    # Engineers submit proposals (technical + financial)
    prop = eng.ok("POST", f"/projects/{p['id']}/proposals", json=proposal_body(400000))
    prop2 = eng2.ok("POST", f"/projects/{p['id']}/proposals", json=proposal_body(450000))
    assert prop["status"] == "submitted"
    eng.call("POST", f"/projects/{p['id']}/proposals", 400, json=proposal_body(900000))  # above budget
    # Engineer tracks status
    assert eng.ok("GET", "/proposals/mine")[0]["status"] == "submitted"
    # Engineers only see their own proposal; the organization sees all
    assert len(eng.ok("GET", f"/projects/{p['id']}/proposals")) == 1
    assert len(owner.ok("GET", f"/projects/{p['id']}/proposals")) == 2

    # 4: review, clarify, shortlist, reject
    owner.ok("POST", f"/proposals/{prop['id']}/decision", json={"decision": "clarify", "note": "How many site visits?"})
    assert eng.ok("GET", f"/proposals/{prop['id']}")["status"] == "clarification_requested"
    eng.ok("POST", f"/proposals/{prop['id']}/clarifications", json={"body": "Two site visits are included."})
    owner.call("POST", f"/proposals/{prop['id']}/accept", 409)                  # can't select while published
    owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "applications_closed"})
    eng.call("POST", f"/projects/{p['id']}/proposals", 409, json=proposal_body())  # closed for proposals
    owner.ok("POST", f"/proposals/{prop['id']}/decision", json={"decision": "shortlist"})
    assert owner.ok("GET", f"/projects/{p['id']}")["status"] == "shortlisted"
    owner.ok("POST", f"/proposals/{prop2['id']}/decision", json={"decision": "reject", "note": "Price"})

    # 5: select the engineer; both confirm the agreement
    proj = owner.ok("POST", f"/proposals/{prop['id']}/accept")
    assert proj["status"] == "proposal_accepted" and proj["agreed_price_cents"] == 400000
    owner.call("POST", f"/projects/{p['id']}/start", 409)                       # engineer hasn't accepted yet
    assert eng.ok("GET", f"/projects/{p['id']}/agreement")["price_cents"] == 400000
    eng.ok("POST", f"/projects/{p['id']}/agreement/accept")
    assert owner.ok("POST", f"/projects/{p['id']}/start")["status"] == "in_progress"
    eng2.call("GET", f"/projects/{p['id']}/milestones", 403)                    # outsiders can't see the workspace

    # 6: milestones (optional, max 6, no minimum value, sum <= price)
    owner.ok("POST", f"/projects/{p['id']}/milestones", json={"title": "Concept", "amount_cents": 0})
    owner.ok("POST", f"/projects/{p['id']}/milestones", json={"title": "Calculations", "amount_cents": 150000})
    owner.call("POST", f"/projects/{p['id']}/milestones", 400, json={"title": "Too much", "amount_cents": 300000})
    for i in range(4):
        owner.ok("POST", f"/projects/{p['id']}/milestones", json={"title": f"M{i}", "amount_cents": 1000})
    owner.call("POST", f"/projects/{p['id']}/milestones", 409, json={"title": "Seventh", "amount_cents": 1})
    ms = owner.ok("GET", f"/projects/{p['id']}/milestones")
    assert len(ms) == 6

    # Tasks
    owner.ok("POST", f"/projects/{p['id']}/tasks", json={"title": "Coordinate grid", "status": "todo"})
    t = eng.ok("GET", f"/projects/{p['id']}/tasks")[0]
    eng.ok("PATCH", f"/tasks/{t['id']}", json={"title": "Coordinate grid", "status": "done"})

    # Deliverable versioning: V1 -> revision requested -> V2 -> approved
    d = owner.ok("POST", f"/projects/{p['id']}/deliverables", json={"title": "Calculation report", "milestone_id": ms[1]["id"]})
    owner.call("POST", f"/deliverables/{d['id']}/versions", 403, files={"file": ("calc.pdf", PDF)})  # only the engineer uploads
    eng.ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("calc-v1.pdf", PDF)}, data={"note": "first"})
    eng.call("POST", f"/projects/{p['id']}/submit", 200, json={"note": "Please review"})
    assert owner.ok("GET", f"/projects/{p['id']}")["status"] == "submitted"
    v1 = owner.ok("GET", f"/projects/{p['id']}/deliverables")[0]["versions"][0]
    owner.call("POST", f"/deliverable-versions/{v1['id']}/review", 400, json={"decision": "revision_requested", "comment": ""})
    owner.ok("POST", f"/deliverable-versions/{v1['id']}/review", json={"decision": "revision_requested", "comment": "Add load combos"})
    owner.call("POST", f"/projects/{p['id']}/approve", 409)                     # not every deliverable approved
    owner.ok("POST", f"/projects/{p['id']}/request-revision", json={"note": "See comments on V1"})
    eng.call("POST", f"/projects/{p['id']}/submit", 409, json={})              # V2 missing
    eng.ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("calc-v2.pdf", PDF)}, data={"note": "fixed"})
    assert eng.ok("POST", f"/projects/{p['id']}/submit", json={})["status"] == "resubmitted"
    versions = owner.ok("GET", f"/projects/{p['id']}/deliverables")[0]["versions"]
    assert [v["version_no"] for v in versions] == [1, 2]                        # V1 kept, never overwritten
    assert versions[0]["review_status"] == "revision_requested" and versions[0]["review_comment"] == "Add load combos"
    owner.ok("POST", f"/deliverable-versions/{versions[1]['id']}/review", json={"decision": "approved", "comment": ""})
    owner.call("POST", f"/deliverable-versions/{versions[0]['id']}/review", 409, json={"decision": "approved", "comment": ""})

    # Milestone approval issues a simulated invoice
    r = owner.ok("POST", f"/milestones/{ms[1]['id']}/approve")
    assert r["invoice"]["subtotal_cents"] == 150000 and r["invoice"]["simulated"]

    # 9: final approval -> invoices for remaining milestones + final balance
    assert owner.ok("POST", f"/projects/{p['id']}/approve")["status"] == "approved"
    fin = owner.ok("GET", f"/projects/{p['id']}/finance")
    assert fin["simulated"] and fin["invoiced_cents"] == 400000                  # whole agreed price invoiced once
    owner.call("POST", f"/projects/{p['id']}/complete", 409)                    # unpaid invoices
    for inv in fin["invoices"]:
        if inv["status"] == "issued":
            owner.ok("POST", f"/invoices/{inv['id']}/pay")
    # fees: organization 2.5% on top, engineer 5% deducted (demo rule)
    paid = owner.ok("GET", f"/projects/{p['id']}/finance")
    big = next(i for i in paid["invoices"] if i["subtotal_cents"] == 150000)
    assert big["org_fee_cents"] == 3750 and big["engineer_fee_cents"] == 7500 and big["engineer_net_cents"] == 142500
    assert owner.ok("POST", f"/projects/{p['id']}/complete")["status"] == "completed"

    # 10 / B8: financial summaries and payment records for both parties
    assert owner.ok("GET", "/finance")["totals"]["paid_cents"] > 0
    eng_fin = eng.ok("GET", "/finance")
    assert eng_fin["totals"]["payouts_pending_cents"] == 400000 - 20000          # 5% engineer fee
    payout = next(t for t in admin.ok("GET", "/admin/finance")["transactions"] if t["kind"] == "payout")
    admin.ok("POST", f"/admin/payouts/{payout['id']}/mark-sent")

    # Two-way ratings after completion
    owner.ok("POST", f"/projects/{p['id']}/ratings", json={"rating": 5, "text": "Great"})
    eng.ok("POST", f"/projects/{p['id']}/ratings", json={"rating": 4, "text": "Good client"})
    owner.call("POST", f"/projects/{p['id']}/ratings", 409, json={"rating": 5})
    assert owner.ok("GET", f"/engineers/{eng.ok('GET', '/auth/me')['id']}")["average_rating"] == 5.0


def test_invalid_transitions_are_refused(world):
    owner, eng = world["owner"], world["eng"]
    p = new_project(owner)
    owner.call("POST", f"/projects/{p['id']}/approve", 409)
    owner.call("POST", f"/projects/{p['id']}/transitions", 409, json={"to": "under_evaluation"})  # draft -> evaluation
    owner.call("POST", f"/projects/{p['id']}/complete", 409)
    eng.call("POST", f"/projects/{p['id']}/submit", 404, json={})              # draft invisible to engineers
    owner.call("POST", f"/projects/{p['id']}/transitions", 422, json={"to": "completed"})       # not a manual step
    owner.call("PATCH", f"/projects/{p['id']}", 422, json={"status": "completed"})             # status can't be set


def test_verification_required_to_publish_and_propose(world):
    admin = world["admin"]
    other = register("organization", "new@example.com", "New Owner", "New Org")
    p = new_project(other)
    r = other.call("POST", f"/projects/{p['id']}/publish", 409)
    assert r.json()["error"]["code"] == "VERIFICATION_REQUIRED"
    newbie = register("engineer", "newbie@example.com", "New Engineer")
    p2 = new_project(world["owner"])
    world["owner"].ok("POST", f"/projects/{p2['id']}/publish")
    r = newbie.call("POST", f"/projects/{p2['id']}/proposals", 409, json=proposal_body())
    assert r.json()["error"]["code"] == "VERIFICATION_REQUIRED"
    _ = admin


def test_org_roles_are_enforced_on_the_server(world):
    owner, eng = world["owner"], world["eng"]
    viewer = invite_member(owner, "viewer@example.com", "viewer")
    reviewer = invite_member(owner, "reviewer@example.com", "technical_reviewer")
    finance = invite_member(owner, "finance@example.com", "finance")
    pm = invite_member(owner, "pm@example.com", "project_manager")
    viewer.call("POST", "/projects", 403, json={"title": "x" * 6, "description": "d" * 25, "work_mode": "remote",
                                                "max_budget_cents": 10000, "deadline": future(5)})
    p, _ = _to_in_progress(world)
    # Project manager can manage, reviewer can review but not select or approve milestones
    pm.ok("POST", f"/projects/{p['id']}/milestones", json={"title": "Stage 1", "amount_cents": 100000})
    d = pm.ok("POST", f"/projects/{p['id']}/deliverables", json={"title": "Report"})
    eng.ok("POST", f"/deliverables/{d['id']}/versions", files={"file": ("r.pdf", PDF)})
    v = reviewer.ok("GET", f"/projects/{p['id']}/deliverables")[0]["versions"][0]
    viewer.call("POST", f"/deliverable-versions/{v['id']}/review", 403, json={"decision": "approved", "comment": ""})
    finance.call("POST", f"/deliverable-versions/{v['id']}/review", 403, json={"decision": "approved", "comment": ""})
    reviewer.ok("POST", f"/deliverable-versions/{v['id']}/review", json={"decision": "approved", "comment": "OK"})
    ms = reviewer.ok("GET", f"/projects/{p['id']}/milestones")
    reviewer.call("POST", f"/milestones/{ms[0]['id']}/approve", 403)
    inv = pm.ok("POST", f"/milestones/{ms[0]['id']}/approve")["invoice"]
    pm.call("POST", f"/invoices/{inv['id']}/pay", 403)                         # PM can't record payments
    viewer.call("GET", "/finance", 403)
    finance.ok("POST", f"/invoices/{inv['id']}/pay")
    # Owner can't demote the last owner
    me = owner.ok("GET", "/organizations/me/members")["members"]
    own = next(m for m in me if m["is_me"])
    owner.call("PATCH", f"/organizations/me/members/{own['id']}", 409, json={"org_role": "viewer"})


def test_unselect_returns_to_evaluation_and_cancel_rejects_proposals(world):
    owner, eng = world["owner"], world["eng"]
    p = new_project(owner)
    owner.ok("POST", f"/projects/{p['id']}/publish")
    prop = eng.ok("POST", f"/projects/{p['id']}/proposals", json=proposal_body())
    owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "applications_closed"})
    owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "under_evaluation"})
    owner.ok("POST", f"/proposals/{prop['id']}/accept")
    assert owner.ok("POST", f"/projects/{p['id']}/unselect")["status"] == "under_evaluation"
    owner.ok("POST", f"/proposals/{prop['id']}/accept")                         # select again, then cancel
    assert owner.ok("POST", f"/projects/{p['id']}/transitions", json={"to": "cancelled"})["status"] == "cancelled"
    assert eng.ok("GET", f"/proposals/{prop['id']}")["status"] == "rejected"
    eng.call("GET", f"/projects/{p['id']}/files", 200)                          # still a bidder: briefs only
    assert eng.ok("GET", f"/projects/{p['id']}")["my_role"] == "bidder"         # no longer 'hired'


def test_engineer_notifications_and_messages(world):
    owner, eng = world["owner"], world["eng"]
    p = new_project(owner)
    owner.ok("POST", f"/projects/{p['id']}/publish")
    eng.ok("POST", f"/projects/{p['id']}/proposals", json=proposal_body())
    assert any(n["kind"] == "proposal_received" for n in owner.ok("GET", "/notifications"))
    org_id = owner.ok("GET", "/organizations/me")["id"]
    conv = eng.ok("POST", "/conversations", json={"org_id": org_id})
    eng.ok("POST", f"/conversations/{conv['id']}/messages", json={"body": "Hello"})
    assert owner.ok("GET", "/notifications/unread-count")["messages"] == 1
    assert owner.ok("GET", f"/conversations/{conv['id']}/messages")[0]["body"] == "Hello"
    stranger = register("engineer", "stranger@example.com")
    stranger.call("POST", "/conversations", 403, json={"org_id": org_id})       # no proposal -> can't message
    stranger.call("GET", f"/conversations/{conv['id']}/messages", 404)
    _ = Client

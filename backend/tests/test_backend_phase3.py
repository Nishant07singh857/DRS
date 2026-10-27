"""
Phase 3 (backend) regression tests — QA report 2026-10-27, section 9.

Covers BE-C1, BE-C2, BE-C4, BE-H1..H10 (backend halves) and BE-M1.
Pure-Python tests + API tests on the same harness as test_security
(in-memory SQLite, db.create_all). The migration-chain test is the
exception: it runs the real Alembic chain on a fresh file DB.
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef01234567")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-0123456789abcdef01234567")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MAX_UPLOAD_MB", "5")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app import create_app, celery
from extensions import db, limiter
from core_processing.drs_logic import analyze_lbw_rules, analyze_lbw_icc
from core_processing.scoring_engine import (
    InningsState, ScoringError, validate_delivery)

PW = "StrongPass123"


@pytest.fixture()
def app(tmp_path):
    application = create_app()
    application.config["TESTING"] = True
    limiter.reset()
    celery.conf.update(
        task_always_eager=True,
        task_store_eager_result=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _user(client, username):
    assert client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@x.com",
              "password": PW},
    ).status_code == 201
    res = client.post(
        "/api/auth/login", json={"username": username, "password": PW})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.get_json()['access_token']}"}


def _team(client, headers, name):
    res = client.post("/api/teams", json={"name": name}, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def _match(client, headers, overs=20, **extra):
    ta = _team(client, headers, "Team A")
    tb = _team(client, headers, "Team B")
    body = {"title": "M1", "team_a_id": ta, "team_b_id": tb,
            "overs_per_innings": overs}
    body.update(extra)
    res = client.post("/api/matches", json=body, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"], ta, tb


def _live_match(client, headers, overs=20):
    mid, ta, tb = _match(client, headers, overs=overs)
    assert client.post(f"/api/matches/{mid}/toss",
                       json={"toss_winner_id": ta, "toss_choice": "bat"},
                       headers=headers).status_code == 200
    res = client.post(f"/api/matches/{mid}/innings",
                      json={"batting_team_id": ta}, headers=headers)
    assert res.status_code == 201, res.get_json()
    return mid, ta, tb, res.get_json()["id"]


def _ball(client, headers, mid, iid, **body):
    return client.post(f"/api/matches/{mid}/innings/{iid}/ball",
                       json=body, headers=headers)


# --------------------------------------------------------------- BE-C1
def _bouncing_traj(release_x, bounce_x, impact_x, width=1000):
    """Trajectory: release -> bounce (y max, ground) -> pad impact.
    x badhta hai bowler se batsman ki taraf; y neeche = ground."""
    xs = []
    # release se bounce tak 8 points, bounce se impact tak 8 points
    for i in range(9):
        xs.append(release_x + (bounce_x - release_x) * i / 8)
    for i in range(1, 9):
        xs.append(bounce_x + (impact_x - bounce_x) * i / 8)
    ys = [100, 130, 160, 190, 220, 250, 280, 310, 340,  # bounce y=340
          320, 315, 312, 310, 309, 308, 307, 306]  # pad y=306, in band
    return list(zip(xs, ys))


def test_pitching_uses_bounce_not_release():
    """BE-C1: release leg ke bahar (x=800 > leg 700) lekin bounce
    in line (x=500) ho to pitching OUTSIDE LEG nahi honi chahiye."""
    traj = _bouncing_traj(release_x=800, bounce_x=500, impact_x=500)
    res = analyze_lbw_rules({'ball': (500, 306), 'trajectory': traj}, 1000)
    assert res is not None
    assert res['pitch_point'][0] == 500  # bounce x, not release x
    assert not any(s['check'] == 'Pitching'
                   and 'OUTSIDE LEG' in s['result'] for s in res['steps'])


def test_no_bounce_is_inconclusive_not_release_judged():
    """BE-C1: bina bounce wali (flat / full-toss) trajectory par
    decision INCONCLUSIVE hai — release point se pitch judge nahi hoti."""
    traj = [(100 + 50 * i, 300) for i in range(11)]
    res = analyze_lbw_rules({'ball': (600, 300), 'trajectory': traj}, 1000)
    assert res is not None
    assert res['final_decision'] == 'INCONCLUSIVE'


# --------------------------------------------------------------- BE-H2
def test_umpires_call_50_percent_rule():
    """BE-H2: hitting overlap < 50% par on-field call stands (Umpire's
    Call). Ball stumps zone (400-600) ke LEFT edge par aati hai:
    bounce outside-off (300) aur impact outside-off (390) no-shot par
    pass hote hain, phir extrapolated path zone me ghusta hai — pehla
    overlapping step centre ~383, radius 20 -> overlap 2.7/40 = 0.07
    (< 0.5) -> marginal -> on-field NOT OUT stands, lekin ball hitting
    thi isliye hitting_wickets True rehta hai (BE-H9)."""
    traj = _bouncing_traj(release_x=100, bounce_x=300, impact_x=390)
    res = analyze_lbw_icc({'ball': (390, 306), 'trajectory': traj}, 1000,
                          playing_shot=False, on_field_call='NOT OUT',
                          ball_radius_px=20.0)
    assert res is not None
    assert res['hitting_wickets'] is True
    assert res['umpires_call'] is True
    assert res['final_decision'] == 'NOT OUT'
    assert res['overlap_fractions']['hitting'] < 0.5


def test_clear_hitting_is_out_not_umpires_call():
    traj = _bouncing_traj(release_x=200, bounce_x=500, impact_x=500)
    res = analyze_lbw_rules({'ball': (500, 306), 'trajectory': traj}, 1000,
                            on_field_call='NOT OUT')
    assert res['final_decision'] == 'OUT'
    assert res['umpires_call'] is False


def test_on_field_call_validated():
    traj = _bouncing_traj(release_x=200, bounce_x=500, impact_x=500)
    with pytest.raises(ValueError):
        analyze_lbw_rules({'ball': (500, 306), 'trajectory': traj}, 1000,
                          on_field_call='MAYBE')


# --------------------------------------------------------------- BE-H3
def test_no_shot_outside_leg_impact_rejected():
    """BE-H3: no-shot par bhi leg stump ke bahar impact NOT OUT hai."""
    traj = _bouncing_traj(release_x=200, bounce_x=500, impact_x=800)
    res = analyze_lbw_rules({'ball': (800, 306), 'trajectory': traj}, 1000,
                            playing_shot=False)
    assert res['final_decision'] == 'NOT OUT'
    assert any(s['check'] == 'Impact' and 'OUTSIDE LEG' in s['result']
               for s in res['steps'])


def test_no_shot_outside_off_impact_passes():
    """BE-H3 control: no-shot + outside-off impact (leg ke andar) pass
    hota hai — label OUTSIDE OFF hi rehta hai."""
    traj = _bouncing_traj(release_x=200, bounce_x=300, impact_x=350)
    res = analyze_lbw_rules({'ball': (350, 306), 'trajectory': traj}, 1000,
                            playing_shot=False)
    assert any(s['check'] == 'Impact'
               and 'OUTSIDE OFF (no shot' in s['result'] for s in res['steps'])


# --------------------------------------------------------------- BE-H1
def test_over_stumps_path_with_in_line_impact():
    """BE-H1: impact in line (x=575, zone 400-600), lekin pre-impact
    segment steeply UPWARD ja raha hai (y 140 -> 100 -> 60) — predicted
    path stump band (ground 340 - 35.5 = 304.5 se neeche) se upar hi
    rehta hai, isliye MISSING, HITTING nahi (purana code sirf x-range
    dekhta tha aur ise HITTING gin leta tha)."""
    traj = [(200 + 25 * i, y) for i, y in enumerate(
        [100, 130, 160, 190, 220, 250, 280, 310, 340,  # bounce i=8, x=400
         300, 260, 220, 180, 140, 100, 60])]
    res = analyze_lbw_rules({'ball': (575, 60), 'trajectory': traj}, 1000,
                            playing_shot=True)
    assert res['hitting_wickets'] is False
    assert res['final_decision'] == 'NOT OUT'


# --------------------------------------------------------------- BE-H9
def test_compat_fields_from_actual_steps():
    """BE-H9: outside-off pitch par pitch_in_line False (pehle True
    tha, kyunki Pitching pass hota tha); Umpire's Call NOT OUT par bhi
    hitting_wickets True jab ball hitting thi."""
    traj = _bouncing_traj(release_x=200, bounce_x=300, impact_x=500)
    res = analyze_lbw_rules({'ball': (500, 306), 'trajectory': traj}, 1000)
    assert res['pitch_in_line'] is False  # OUTSIDE OFF, pass phir bhi
    assert res['impact_in_line'] is True
    assert res['hitting_wickets'] is True
    assert res['final_decision'] == 'OUT'


# --------------------------------------------------------------- BE-H4
def test_noball_bat_runs_credited_to_batter():
    """BE-H4: no-ball par bat runs batter ko milte hain."""
    st = InningsState()
    st.set_batters(1, 2)
    st.set_bowler(3)
    st.add_ball(runs_off_bat=4, extras={'noball': 1})
    assert st.batters[1]['runs'] == 4
    assert st.batters[1]['balls'] == 0  # ball count nahi hoti
    assert st.bowlers[3]['runs'] == 5


def test_bowler_wicket_only_for_bowlers_wickets():
    st = InningsState()
    st.set_batters(1, 2)
    st.set_bowler(3)
    st.add_ball(is_wicket=True, wicket_type='retired')
    assert st.bowlers[3]['wickets'] == 0
    st2 = InningsState()
    st2.set_batters(1, 2)
    st2.set_bowler(3)
    st2.add_ball(is_wicket=True, wicket_type='bowled')
    assert st2.bowlers[3]['wickets'] == 1


def test_validate_delivery_exclusivity():
    with pytest.raises(ScoringError):
        validate_delivery(runs_off_bat=2, extras={'bye': 1})
    with pytest.raises(ScoringError):
        validate_delivery(extras={'wide': 1, 'legbye': 1})
    with pytest.raises(ScoringError):
        validate_delivery(runs_off_bat=2, is_wicket=True,
                          wicket_type='bowled')
    with pytest.raises(ScoringError):
        validate_delivery(extras={'penalty': 6})
    # Ye valid rehne chahiye: run-out par runs, penalty 5, no-ball run-out.
    validate_delivery(runs_off_bat=2, is_wicket=True, wicket_type='runout')
    validate_delivery(extras={'penalty': 5})
    validate_delivery(extras={'noball': 1}, is_wicket=True,
                      wicket_type='runout')


def test_innings_state_over_guard():
    st = InningsState(max_overs=1)
    for _ in range(6):
        st.add_ball()
    assert st.is_innings_over() is True
    with pytest.raises(ScoringError):
        st.add_ball()


# --------------------------------------------------------------- BE-C2
def test_migration_chain_creates_all_tables(tmp_path):
    """BE-C2: asli Alembic chain ek fresh DB par chalao (create_all nahi)
    — har model table ban-ni chahiye, aur calibration_profiles ka FK
    cameras par hona chahiye (cameras pehle banti hai)."""
    from sqlalchemy import create_engine, inspect
    from alembic.config import Config as AConfig
    from alembic import command
    from config import Config

    db_path = tmp_path / "mig.db"
    # Engine app creation ke dauran cache ho jaata hai (Flask-SQLAlchemy
    # _app_engines), isliye file URL create_app KE BAAD set karne se
    # kuch nahi hota — config subclass se pehle se hi file URL do.
    class MigConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"

    application = create_app(MigConfig)
    application.config["TESTING"] = True
    with application.app_context():
        cfg = AConfig()
        cfg.set_main_option(
            "script_location",
            os.path.join(os.path.dirname(__file__), "..", "migrations"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(cfg, "head")
    insp = inspect(create_engine(f"sqlite:///{db_path}"))
    tables = set(insp.get_table_names())
    expected = {
        'users', 'reviews', 'organizations', 'venues', 'teams', 'players',
        'matches', 'innings', 'deliveries', 'cameras',
        'calibration_profiles', 'bookmarks', 'highlights',
        'notifications', 'audit_logs', 'training_sessions',
        'delivery_metrics', 'revoked_tokens', 'task_ownership',
    }
    missing = expected - tables
    assert not missing, f"migration chain me ye tables nahi bani: {missing}"
    fks = insp.get_foreign_keys('calibration_profiles')
    assert any(fk['referred_table'] == 'cameras' for fk in fks)
    # Security columns bhi chain se aane chahiye.
    assert 'user_id' in {c['name'] for c in insp.get_columns('teams')}
    assert 'user_id' in {c['name'] for c in insp.get_columns('matches')}
    assert 'user_id' in {c['name'] for c in insp.get_columns('cameras')}
    assert 'user_id' in {c['name'] for c in insp.get_columns('highlights')}
    assert 'total_legal_balls' in {c['name']
                                   for c in insp.get_columns('innings')}


# -------------------------------------------------- BE-C4 / BE-H5 (API)
def test_add_ball_innings_over_rejected(client):
    """BE-C4: 1-over match me 6 legal balls ke baad 7th ball reject."""
    h = _user(client, "scorer1")
    mid, ta, tb, iid = _live_match(client, h, overs=1)
    for _ in range(6):
        res = _ball(client, h, mid, iid, runs_off_bat=0)
        assert res.status_code == 201, res.get_json()
    res = _ball(client, h, mid, iid, runs_off_bat=1)
    assert res.status_code == 400, res.get_json()


def test_add_ball_wicket_limit_rejected(client):
    h = _user(client, "wicketkeeper")
    mid, ta, tb, iid = _live_match(client, h, overs=20)
    for _ in range(10):
        res = _ball(client, h, mid, iid, is_wicket=True, wicket_type='bowled')
        assert res.status_code == 201, res.get_json()
    res = _ball(client, h, mid, iid, runs_off_bat=0)
    assert res.status_code == 400


def test_illegal_ball_labelling_and_totals(client):
    """BE-H5: pehli ball wide ho to ball_in_over=1 (pehle 6 milta tha);
    total_balls wide ko ginta hai, total_legal_balls nahi, aur
    total_overs/run_rate legal balls se agree karte hain."""
    h = _user(client, "scorer2")
    mid, ta, tb, iid = _live_match(client, h, overs=20)
    res = _ball(client, h, mid, iid, extras={'wide': 1})
    assert res.status_code == 201, res.get_json()
    d = res.get_json()['delivery']
    inn = res.get_json()['innings']
    assert d['ball_in_over'] == 1 and d['over_number'] == 0
    assert inn['total_balls'] == 1 and inn['total_legal_balls'] == 0
    assert inn['total_overs'] == 0.0 and inn['run_rate'] == 0
    res = _ball(client, h, mid, iid, runs_off_bat=6)
    inn = res.get_json()['innings']
    assert inn['total_balls'] == 2 and inn['total_legal_balls'] == 1
    # 7 runs / 1 legal ball = 42.0 run rate (wide run included, wide
    # ball legal count me nahi — yahi BE-H5 consistency hai).
    assert inn['total_overs'] == 0.1 and inn['run_rate'] == 42.0


# --------------------------------------------------------------- BE-H10
def test_match_validation(client):
    h = _user(client, "valuser")
    ta = _team(client, h, "Team A")
    tb = _team(client, h, "Team B")
    # Same team
    res = client.post("/api/matches",
                      json={"title": "X", "team_a_id": ta, "team_b_id": ta},
                      headers=h)
    assert res.status_code == 400
    # Bad scheduled_at
    res = client.post("/api/matches",
                      json={"title": "X", "team_a_id": ta, "team_b_id": tb,
                            "scheduled_at": "not-a-date"},
                      headers=h)
    assert res.status_code == 400
    # Bad venue FK
    res = client.post("/api/matches",
                      json={"title": "X", "team_a_id": ta, "team_b_id": tb,
                            "venue_id": 9999},
                      headers=h)
    assert res.status_code == 404
    # Valid ISO scheduled_at
    res = client.post("/api/matches",
                      json={"title": "X", "team_a_id": ta, "team_b_id": tb,
                            "scheduled_at": "2026-11-01T10:00:00"},
                      headers=h)
    assert res.status_code == 201, res.get_json()


def test_toss_and_innings_guards(client):
    h = _user(client, "guarduser")
    mid, ta, tb = _match(client, h)
    # Bina toss innings nahi
    res = client.post(f"/api/matches/{mid}/innings",
                      json={"batting_team_id": ta}, headers=h)
    assert res.status_code == 400
    # Toss ok, re-toss reject
    assert client.post(f"/api/matches/{mid}/toss",
                       json={"toss_winner_id": ta, "toss_choice": "bat"},
                       headers=h).status_code == 200
    res = client.post(f"/api/matches/{mid}/toss",
                      json={"toss_winner_id": tb, "toss_choice": "bowl"},
                      headers=h)
    assert res.status_code == 400
    # Innings 1 live hote hue innings 2 nahi
    res = client.post(f"/api/matches/{mid}/innings",
                      json={"batting_team_id": ta}, headers=h)
    assert res.status_code == 201
    res = client.post(f"/api/matches/{mid}/innings",
                      json={"batting_team_id": tb}, headers=h)
    assert res.status_code == 400


# --------------------------------------------------------------- BE-H6
def _review(client, headers, original_call="OUT"):
    body = {"review_type": "LBW"}
    if original_call is not None:
        body["original_call"] = original_call
    res = client.post("/api/reviews/request", json=body, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def _complete(client, headers, rid, rec, conf=90):
    return client.post(f"/api/reviews/{rid}/complete",
                       json={"ai_recommendation": rec, "ai_confidence": conf},
                       headers=headers)


def test_review_accept_reject_validation(client):
    h = _user(client, "ump1")
    # INCONCLUSIVE accept reject hota hai
    rid = _review(client, h)
    assert _complete(client, h, rid, "INCONCLUSIVE", 40).status_code == 200
    res = client.post(f"/api/reviews/{rid}/confirm",
                      json={"action": "accept"}, headers=h)
    assert res.status_code == 400
    # Reject with NULL original_call reject hota hai (NOT OUT invent nahi)
    rid2 = _review(client, h, original_call=None)
    assert _complete(client, h, rid2, "OUT", 90).status_code == 200
    res = client.post(f"/api/reviews/{rid2}/confirm",
                      json={"action": "reject"}, headers=h)
    assert res.status_code == 400
    # Reject with stored original_call -> original_call hi final hai
    rid3 = _review(client, h, original_call="NOT OUT")
    assert _complete(client, h, rid3, "OUT", 90).status_code == 200
    res = client.post(f"/api/reviews/{rid3}/confirm",
                      json={"action": "reject"}, headers=h)
    assert res.status_code == 200
    assert res.get_json()["final_decision"] == "NOT OUT"
    # String confidence -> 400, 500 nahi
    rid4 = _review(client, h)
    res = _complete(client, h, rid4, "OUT", conf="high")
    assert res.status_code == 400


def test_review_retry_clears_decision(client):
    h = _user(client, "ump2")
    rid = _review(client, h)
    # Failed review banao: pending -> processing -> failed nahi ja sakta
    # direct API se, isliye workflow ko seedha failed par le jaane ke
    # liye review ko pehle complete karo phir DB me failed set karo?
    # Simpler: retry sirf failed se allowed hai — is test me review ko
    # failed state me laane ke liye ReviewWorkflow ka use karo.
    from core_processing.review_workflow import ReviewWorkflow
    from models.review import Review
    assert _complete(client, h, rid, "OUT", 90).status_code == 200
    # completed -> failed allowed nahi hai workflow me; isliye retry ka
    # clear-behaviour DB-level verify karte hain: review ko failed
    # banao (seedha DB update, kyunki API se failed state me jaane ka
    # rasta retry ke alawa nahi hai) phir retry karo.
    rv = Review.query.get(rid)
    rv.status = 'failed'
    db.session.commit()
    res = client.post(f"/api/reviews/{rid}/retry", json={}, headers=h)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["status"] == "pending"
    assert body["ai_recommendation"] is None
    assert body["decision"] == "PENDING"
    assert body["confidence"] is None


# --------------------------------------------------------------- BE-H9
def test_single_serializer_keys_match(client):
    """BE-H9: list/detail aur queue/to_dict ek hi serializer dete hain —
    detail me delivery_id aur video_url dono hone chahiye."""
    h = _user(client, "seruser")
    rid = _review(client, h)
    detail = client.get(f"/api/reviews/{rid}", headers=h).get_json()
    assert "delivery_id" in detail and "video_url" in detail
    assert detail["review_type"] == "LBW"  # stored value, mask nahi
    queue = client.get("/api/reviews/queue", headers=h).get_json()
    assert len(queue) == 1
    assert set(queue[0].keys()) == set(detail.keys())


# --------------------------------------------------------------- BE-H8
def test_pitch_map_endpoint(client):
    h = _user(client, "pmuser")
    res = client.post("/api/reviews/pitch-map",
                      json={"bowler_name": "Bumrah", "deliveries": [
                          {"pitch_x": 2.5, "pitch_y": 0.1, "outcome": "dot",
                           "speed_kmh": 135},
                          {"pitch_x": 5.0, "pitch_y": -0.2,
                           "outcome": "wicket", "speed_kmh": 142}]},
                      headers=h)
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["stats"]["total"] == 2
    assert body["svg"].startswith("<svg")
    res = client.post("/api/reviews/pitch-map",
                      json={"deliveries": [{"pitch_x": "bad"}]}, headers=h)
    assert res.status_code == 400
    # BE-M6: dot-ball % me wide count nahi hota (dot 1 / counted 2 = 50,
    # pehle 1/3 = 33.3 hota); pitch_x range se bahar 400 deta hai.
    res = client.post("/api/reviews/pitch-map",
                      json={"deliveries": [
                          {"pitch_x": 2.5, "pitch_y": 0.1, "outcome": "dot"},
                          {"pitch_x": 1.0, "pitch_y": 0.5, "outcome": "wide"},
                          {"pitch_x": 5.0, "pitch_y": -0.2, "outcome": "wicket"}]},
                      headers=h)
    assert res.status_code == 200
    assert res.get_json()["stats"]["dot_ball_pct"] == 50.0
    res = client.post("/api/reviews/pitch-map",
                      json={"deliveries": [{"pitch_x": 25, "pitch_y": 0}]},
                      headers=h)
    assert res.status_code == 400


def test_over_summary_endpoint_row_columns(client):
    """BE-H8: HTML table ki har row me header jitne (6) <td> hon."""
    h = _user(client, "osuser")
    res = client.post("/api/reviews/over-summary",
                      json={"over_number": 1, "bowler": "B", "batsman": "K",
                            "balls": [
                                {"outcome": "dot", "runs": 0, "decision": "NOT OUT",
                                 "delivery_analysis": {"speed_kmh": 135,
                                                       "delivery_type": "Good length"},
                                 "line": "Off stump"},
                                {"outcome": "wicket", "runs": 0, "decision": "OUT",
                                 "delivery_analysis": {"speed_kmh": 140,
                                                       "delivery_type": "Yorker"},
                                 "line": "Middle"}]},
                      headers=h)
    assert res.status_code == 200, res.get_json()
    html = res.get_json()["html"]
    rows = [r for r in html.split("<tr>") if "<td>" in r]
    assert len(rows) == 2
    for r in rows:
        assert r.count("<td>") == 6, r
    assert res.get_json()["summary"]["runs"] == 0
    assert res.get_json()["summary"]["wickets"] == 1


# ---------------------------------------------------------- BE-M1 / BE-H7
def test_live_returns_pending_review_id(client):
    """BE-M1: /live ke drs block me pending review ki id aani chahiye."""
    h = _user(client, "liveuser")
    mid, ta, tb = _match(client, h)
    res = client.get(f"/api/matches/{mid}/live", headers=h)
    assert res.status_code == 200
    assert res.get_json()["live"] is None
    # Match par review request karo (match_id ke saath, pending)
    res = client.post("/api/reviews/request",
                      json={"review_type": "LBW", "original_call": "OUT",
                            "match_id": mid}, headers=h)
    assert res.status_code == 201
    rid = res.get_json()["id"]
    # Live ke liye innings chahiye — toss + innings shuru karo
    client.post(f"/api/matches/{mid}/toss",
                json={"toss_winner_id": ta, "toss_choice": "bat"}, headers=h)
    client.post(f"/api/matches/{mid}/innings",
                json={"batting_team_id": ta}, headers=h)
    res = client.get(f"/api/matches/{mid}/live", headers=h)
    assert res.get_json()["live"]["drs"]["review_id"] == rid
    assert res.get_json()["live"]["drs"]["pending_reviews"] == 1
    # BE-M1 detail: players + ball ke baad batters/bowlers detail bhari
    # honi chahiye (pehle hamesha khaali rehti thi).
    p1 = client.post(f"/api/teams/{ta}/players", json={"name": "Striker"},
                     headers=h).get_json()["id"]
    p2 = client.post(f"/api/teams/{ta}/players", json={"name": "NonStriker"},
                     headers=h).get_json()["id"]
    p3 = client.post(f"/api/teams/{tb}/players", json={"name": "Bowler"},
                     headers=h).get_json()["id"]
    iid = res.get_json()["live"]["id"]
    assert _ball(client, h, mid, iid, runs_off_bat=1, striker_id=p1,
                 non_striker_id=p2, bowler_id=p3).status_code == 201
    live = client.get(f"/api/matches/{mid}/live", headers=h).get_json()["live"]
    assert {b["name"] for b in live["batters_detail"]} == {"Striker", "NonStriker"}
    assert [b["name"] for b in live["bowlers_detail"]] == ["Bowler"]


def test_final_lbw_decision_helper_passes_evidence():
    """BE-H7 helper: explicit bat/no-ball evidence pass hoti hai, aur
    trajectory na ho to None milta hai (koi silent decision nahi)."""
    from tasks import _final_lbw_decision
    traj = _bouncing_traj(release_x=200, bounce_x=500, impact_x=500)
    tracking = {'ball': (500, 306), 'trajectory': traj}
    res = _final_lbw_decision(tracking, 1000, None, 30)
    assert res is not None and res['final_decision'] == 'OUT'
    # Bat evidence mile to NOT OUT (bat-first)
    res2 = _final_lbw_decision({**tracking, 'bat_involved': True},
                               1000, None, 30)
    assert res2['final_decision'] == 'NOT OUT'
    # No-ball evidence mile to NOT OUT
    res3 = _final_lbw_decision({**tracking, 'is_no_ball': True},
                               1000, None, 30)
    assert res3['final_decision'] == 'NOT OUT'
    assert _final_lbw_decision({'ball': None, 'trajectory': []},
                               1000, None, 30) is None
    assert _final_lbw_decision(None, 1000, None, 30) is None

"""
Match Management API — RESTful endpoints for StreetDRS match infrastructure.

Endpoints:
  POST   /api/matches              — naya match banao
  GET    /api/matches              — match list
  GET    /api/matches/<id>         — match detail + live score
  POST   /api/matches/<id>/toss    — toss record karo
  POST   /api/matches/<id>/innings — nayi innings shuru karo
  POST   /api/matches/<id>/innings/<iid>/ball — ball add karo (scoring!)
  GET    /api/matches/<id>/scorecard — poora scorecard

  POST   /api/teams                — team banao
  POST   /api/teams/<id>/players   — player add karo
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from extensions import db, limiter
from api.routes.common import current_user_id
from models.match import (Organization, Venue, Team, Player, Match,
                          Innings, Delivery)
from core_processing.scoring_engine import InningsState, ScoringError

matches_bp = Blueprint('matches', __name__)


def _parse_scheduled_at(raw):
    """scheduled_at JSON string → datetime, ya None. Galat format par
    ValueError (route 400 deta hai — pehle raw string DateTime column
    me jaakar commit par 500 deta tha aur session dirty chhodta tha)."""
    if raw is None or raw == '':
        return None
    if isinstance(raw, str):
        from datetime import datetime
        text = raw.strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(
                f"scheduled_at ISO format me hona chahiye, mila: {raw!r}")
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    raise ValueError(f"scheduled_at string hona chahiye, mila: {type(raw)}")


# --- Teams ---

@matches_bp.route('/teams', methods=['POST'])
@jwt_required()
def create_team():
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'message': 'Team name zaroori hai'}), 400
    # BE-H10: organization_id diya hai to wo exist karna chahiye (FK
    # violation par 500 ki jagah saaf 404).
    if data.get('organization_id') is not None and not Organization.query.get(
            data['organization_id']):
        return jsonify({'message': 'Organization nahi mili'}), 404
    team = Team(
        name=data['name'],
        short_name=data.get('short_name', data['name'][:3].upper()),
        organization_id=data.get('organization_id'),
        # SEC-C3: creator hi owner hai.
        user_id=current_user_id(),
    )
    db.session.add(team)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'Team banane me error'}), 500
    return jsonify(team.to_dict()), 201


@matches_bp.route('/teams/<int:team_id>/players', methods=['POST'])
@jwt_required()
def add_player(team_id):
    # SEC-C3: sirf team owner hi player add kar sakta hai.
    team = Team.query.filter_by(id=team_id, user_id=current_user_id()).first_or_404()
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'message': 'Player name zaroori hai'}), 400
    player = Player(
        team_id=team.id,
        name=data['name'],
        jersey_number=data.get('jersey_number'),
        batting_style=data.get('batting_style'),
        bowling_style=data.get('bowling_style'),
        player_role=data.get('player_role', 'batter'),
    )
    db.session.add(player)
    db.session.commit()
    return jsonify(player.to_dict()), 201


# --- Matches ---

@matches_bp.route('/matches', methods=['POST'])
@jwt_required()
def create_match():
    data = request.get_json() or {}
    for f in ['title', 'team_a_id', 'team_b_id']:
        if not data.get(f):
            return jsonify({'message': f'{f} zaroori hai'}), 400

    # Teams exist karte hain? SEC-C3: sirf apni teams use ho sakti
    # hain — doosre user ki team se match banana bhi cross-tenant hai.
    uid = current_user_id()
    # BE-H10: ek hi team khud se nahi khel sakti.
    if data['team_a_id'] == data['team_b_id']:
        return jsonify({'message': 'Team A aur Team B alag hone chahiye'}), 400
    if not Team.query.filter_by(id=data['team_a_id'], user_id=uid).first():
        return jsonify({'message': 'Team A nahi mili'}), 404
    if not Team.query.filter_by(id=data['team_b_id'], user_id=uid).first():
        return jsonify({'message': 'Team B nahi mili'}), 404
    # BE-H10: venue/organization IDs bhi exist karne chahiye.
    if data.get('venue_id') is not None and not Venue.query.get(
            data['venue_id']):
        return jsonify({'message': 'Venue nahi mila'}), 404
    if data.get('organization_id') is not None and not Organization.query.get(
            data['organization_id']):
        return jsonify({'message': 'Organization nahi mili'}), 404
    try:
        scheduled_at = _parse_scheduled_at(data.get('scheduled_at'))
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    overs = data.get('overs_per_innings', 20)
    if isinstance(overs, bool) or not isinstance(overs, int) or overs <= 0:
        return jsonify({'message': 'overs_per_innings positive integer hona chahiye'}), 400

    match = Match(
        user_id=uid,
        title=data['title'],
        team_a_id=data['team_a_id'],
        team_b_id=data['team_b_id'],
        venue_id=data.get('venue_id'),
        organization_id=data.get('organization_id'),
        match_format=data.get('match_format', 'T20'),
        overs_per_innings=overs,
        scheduled_at=scheduled_at,
        config=data.get('config', {}),
    )
    db.session.add(match)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'Match banane me error'}), 500
    return jsonify(match.to_dict()), 201


@matches_bp.route('/matches', methods=['GET'])
@jwt_required()
def list_matches():
    status = request.args.get('status')
    # SEC-C3: sirf apne matches.
    q = Match.query.filter_by(user_id=current_user_id())
    if status:
        q = q.filter_by(status=status)
    matches = q.order_by(Match.created_at.desc()).limit(50).all()
    return jsonify([m.to_dict() for m in matches])


@matches_bp.route('/matches/<int:match_id>', methods=['GET'])
@jwt_required()
def get_match(match_id):
    match = Match.query.filter_by(id=match_id, user_id=current_user_id()).first_or_404()
    d = match.to_dict()
    d['innings'] = [i.to_dict() for i in match.innings]
    return jsonify(d)


@matches_bp.route('/matches/<int:match_id>/toss', methods=['POST'])
@jwt_required()
def record_toss(match_id):
    match = Match.query.filter_by(id=match_id, user_id=current_user_id()).first_or_404()
    data = request.get_json() or {}
    winner_id = data.get('toss_winner_id')
    choice = data.get('toss_choice')  # bat/bowl

    # BE-H10: toss sirf ek baar, sirf scheduled match par — re-toss
    # overwrite nahi karta, aur completed match ko 'live' nahi banata.
    if match.toss_winner_id is not None:
        return jsonify({'message': 'Toss pehle hi ho chuka hai'}), 400
    if match.status != 'scheduled':
        return jsonify({'message': f'Toss sirf scheduled match par hota hai (current: {match.status})'}), 400
    if winner_id not in [match.team_a_id, match.team_b_id]:
        return jsonify({'message': 'Winner team match me nahi hai'}), 400
    if choice not in ['bat', 'bowl']:
        return jsonify({'message': 'Choice bat ya bowl hona chahiye'}), 400

    match.toss_winner_id = winner_id
    match.toss_choice = choice
    match.status = 'live'
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'Toss record karne me error'}), 500
    return jsonify(match.to_dict())


@matches_bp.route('/matches/<int:match_id>/innings', methods=['POST'])
@jwt_required()
def start_innings(match_id):
    match = Match.query.filter_by(id=match_id, user_id=current_user_id()).first_or_404()
    data = request.get_json() or {}

    # BE-H10: innings transitions — toss zaroori, pichhli innings
    # complete zaroori, do innings ek saath live nahi, aur innings 2
    # me wahi team dobara batting nahi kar sakti.
    if match.status == 'completed':
        return jsonify({'message': 'Match complete ho chuka hai'}), 400
    if match.toss_winner_id is None:
        return jsonify({'message': 'Pehle toss record karo'}), 400
    for inn in match.innings:
        if inn.status == 'live':
            return jsonify({'message': 'Ek innings pehle hi live hai'}), 400
    innings_num = len(match.innings) + 1
    if innings_num > 2:
        return jsonify({'message': '2 se zyada innings nahi!'}), 400

    batting_id = data.get('batting_team_id')
    if batting_id not in [match.team_a_id, match.team_b_id]:
        return jsonify({'message': 'Batting team match me nahi hai'}), 400
    if innings_num == 2:
        prev = match.innings[0]
        if prev.status != 'completed':
            return jsonify({'message': 'Pehli innings abhi complete nahi hui'}), 400
        if batting_id == prev.batting_team_id:
            return jsonify({'message': 'Innings 2 me doosri team batting karegi'}), 400

    bowling_id = match.team_b_id if batting_id == match.team_a_id else match.team_a_id

    innings = Innings(
        match_id=match.id,
        innings_number=innings_num,
        batting_team_id=batting_id,
        bowling_team_id=bowling_id,
        status='live',
    )
    db.session.add(innings)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'Innings shuru karne me error'}), 500
    return jsonify(innings.to_dict()), 201


@matches_bp.route('/matches/<int:match_id>/innings/<int:innings_id>/ball',
                  methods=['POST'])
@jwt_required()
@limiter.limit("60 per minute")  # scorer tez hai, lekin abuse nahi
def add_ball(match_id, innings_id):
    """
    Ball-by-ball scoring! Sabse important endpoint.

    Body: {
        "runs_off_bat": 4,
        "extras": {"wide": 0, "noball": 0, "bye": 0, "legbye": 0},
        "is_wicket": false,
        "wicket_type": null,
        "bowler_id": 10, "striker_id": 1, "non_striker_id": 2
    }
    """
    # SEC-C3: match owner hi ball add kar sakta hai.
    # BE-C4: innings row par row-lock (Postgres par FOR UPDATE; SQLite
    # par no-op) — concurrent scorers ek hi innings par ball number /
    # totals race nahi kar sakte, kyunki doosra writer pehle writer ke
    # commit ke baad hi lock paata hai aur tab updated state dekhta hai.
    match = Match.query.filter_by(id=match_id, user_id=current_user_id()).first_or_404()
    innings = Innings.query.filter_by(id=innings_id,
                                      match_id=match.id).with_for_update().first_or_404()
    data = request.get_json() or {}

    # BE-C4: status guards — khatam innings / match par ball nahi.
    if match.status in ('completed', 'abandoned'):
        return jsonify({'message': f'Match {match.status} hai — ball add nahi ho sakti'}), 400
    if innings.status != 'live':
        return jsonify({'message': f'Innings {innings.status} hai — ball add nahi ho sakti'}), 400

    # BE-C4: SAB scoring ek InningsState se guzregi — pehle code sirf
    # validate_delivery call karke haath se totals badhata tha aur
    # is_innings_over() kabhi consult hi nahi karta tha, isliye innings
    # 20 overs / 10 wickets ke paar bhi chalti rehti thi.
    max_overs = match.overs_per_innings or 20
    state = InningsState(max_overs=max_overs, max_wickets=10)
    # DB totals se state seed karo (legal-ball count legacy rows par
    # deliveries gin kar nikalo, warna stored total_legal_balls se).
    legal_before = innings.total_legal_balls
    if legal_before is None:
        legal_before = Delivery.query.filter_by(innings_id=innings.id,
                                                is_legal=True).count()
    state.runs = innings.total_runs or 0
    state.wickets = innings.total_wickets or 0
    state.legal_balls = legal_before
    state.total_balls = innings.total_balls or 0
    if data.get('striker_id') and data.get('non_striker_id'):
        state.set_batters(data['striker_id'], data['non_striker_id'])
    if data.get('bowler_id'):
        state.set_bowler(data['bowler_id'])
    try:
        summary = state.add_ball(
            runs_off_bat=data.get('runs_off_bat', 0),
            extras=data.get('extras', {}),
            is_wicket=data.get('is_wicket', False),
            wicket_type=data.get('wicket_type'),
            out_player_id=data.get('out_player_id'),
        )
    except ScoringError as e:
        db.session.rollback()
        return jsonify({'message': f'Scoring error: {e}'}), 400
    total_runs = summary['total_runs_this_ball']
    is_legal = summary['is_legal']

    # Ball numbering — locked innings ke andar, isi transaction me.
    last = Delivery.query.filter_by(innings_id=innings.id)\
                         .order_by(Delivery.ball_number.desc()).first()
    ball_number = (last.ball_number + 1) if last else 1

    # BE-H5: ball_in_over hamesha "agle legal ball ka number" hai —
    # legal ho ya illegal. Pehle illegal ball par (legal_count % 6 or 6)
    # likha jaata tha: innings ki pehli ball wide hoti to ball_in_over=6
    # milta tha, aur over poora hone ke baad wide pichhle over ke 6th
    # ball ka label duplicate karta tha.
    over_number = legal_before // 6
    ball_in_over = (legal_before % 6) + 1

    delivery = Delivery(
        innings_id=innings.id,
        match_id=match_id,
        over_number=over_number,
        ball_number=ball_number,
        ball_in_over=ball_in_over,
        bowler_id=data.get('bowler_id'),
        striker_id=data.get('striker_id'),
        non_striker_id=data.get('non_striker_id'),
        runs_off_bat=data.get('runs_off_bat', 0),
        extras=data.get('extras', {}),
        total_runs=total_runs,
        is_wicket=data.get('is_wicket', False),
        wicket_type=data.get('wicket_type'),
        out_player_id=data.get('out_player_id'),
        is_legal=is_legal,
        tracking_data=data.get('tracking_data'),  # AI se aaya to
    )
    db.session.add(delivery)

    # Innings totals — state se, haath se nahi. total_overs HAR ball
    # par legal balls se dobara nikalta hai (pehle sirf legal ball par
    # update hota tha, isliye wide/no-ball ke baad stale ho jaata tha).
    innings.total_runs = state.runs
    innings.total_wickets = state.wickets
    innings.total_balls = state.total_balls
    innings.total_legal_balls = state.legal_balls
    innings.total_overs = state.legal_balls // 6 + (state.legal_balls % 6) / 10
    if state.is_innings_over():
        innings.status = 'completed'
        # Innings 2 khatam = match khatam; innings 1 khatam par match
        # innings 2 ka intezar karta hai.
        if innings.innings_number >= 2:
            match.status = 'completed'

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'Ball save karne me error'}), 500

    return jsonify({
        'delivery': delivery.to_dict(),
        'innings': innings.to_dict(),
    }), 201


@matches_bp.route('/matches/<int:match_id>/scorecard', methods=['GET'])
@jwt_required()
def get_scorecard(match_id):
    """Poora match scorecard."""
    match = Match.query.filter_by(id=match_id, user_id=current_user_id()).first_or_404()
    result = match.to_dict()
    result['innings_detail'] = []
    for inn in match.innings:
        d = inn.to_dict()
        d['deliveries'] = [deliv.to_dict() for deliv in inn.deliveries]
        result['innings_detail'].append(d)
    return jsonify(result)


@matches_bp.route('/matches/<int:match_id>/live', methods=['GET'])
@jwt_required()
def live_match_center(match_id):
    """
    D. Live Match Center — ek endpoint me sab kuch!
    Scoreboard, batters, bowler, recent balls, DRS status, system health.
    """
    from models.review import Review
    match = Match.query.filter_by(id=match_id, user_id=current_user_id()).first_or_404()

    # Current innings (live wali)
    current_inn = None
    for inn in match.innings:
        if inn.status == 'live':
            current_inn = inn
            break
    if not current_inn and match.innings:
        current_inn = match.innings[-1]

    result = match.to_dict()
    result['live'] = None

    if current_inn:
        # Recent 12 balls
        recent = Delivery.query.filter_by(innings_id=current_inn.id)\
                              .order_by(Delivery.ball_number.desc())\
                              .limit(12).all()
        # Is over ki balls
        live = current_inn.to_dict()
        live['recent_balls'] = [d.to_dict() for d in reversed(recent)]

        # Batter/Bowler detail (player names ke saath) — BE-M1: pehle
        # ye hamesha khaali rehta tha. Aakhri delivery ke striker /
        # non-striker / bowler se bharo (koi delivery nahi to khaali).
        live['batters_detail'] = []
        live['bowlers_detail'] = []
        if recent:
            last = recent[0]  # ball_number desc order me pehla = aakhri
            for pid, role in ((last.striker_id, 'striker'),
                              (last.non_striker_id, 'non_striker')):
                if pid:
                    p = Player.query.get(pid)
                    if p:
                        live['batters_detail'].append(
                            {'player_id': p.id, 'name': p.name, 'role': role})
            if last.bowler_id:
                p = Player.query.get(last.bowler_id)
                if p:
                    live['bowlers_detail'].append(
                        {'player_id': p.id, 'name': p.name, 'role': 'bowler'})

        # DRS status (N)
        # BE-M1: frontend LiveMatch → ReviewCenter link ke liye pending
        # review ki id bhi do (pehle sirf count tha, isliye link hamesha
        # /reviews par girta tha). Koi pending review nahi to None.
        pending_q = Review.query.filter(
            Review.match_id == match_id,
            Review.status.in_(['pending', 'processing'])
        )
        pending_reviews = pending_q.count()
        latest_pending = pending_q.order_by(
            Review.created_at.desc()).first()
        live['drs'] = {
            'pending_reviews': pending_reviews,
            'status': 'review_pending' if pending_reviews > 0 else 'idle',
            'review_id': latest_pending.id if latest_pending else None,
        }
        result['live'] = live

    # Team names
    team_a = Team.query.get(match.team_a_id)
    team_b = Team.query.get(match.team_b_id)
    result['team_a_name'] = team_a.name if team_a else '?'
    result['team_b_name'] = team_b.name if team_b else '?'

    return jsonify(result), 200

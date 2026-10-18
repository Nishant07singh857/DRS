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
from models.match import (Organization, Venue, Team, Player, Match,
                          Innings, Delivery)
from core_processing.scoring_engine import InningsState, ScoringError

matches_bp = Blueprint('matches', __name__)


# --- Teams ---

@matches_bp.route('/teams', methods=['POST'])
@jwt_required()
def create_team():
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'message': 'Team name zaroori hai'}), 400
    team = Team(
        name=data['name'],
        short_name=data.get('short_name', data['name'][:3].upper()),
        organization_id=data.get('organization_id'),
    )
    db.session.add(team)
    db.session.commit()
    return jsonify(team.to_dict()), 201


@matches_bp.route('/teams/<int:team_id>/players', methods=['POST'])
@jwt_required()
def add_player(team_id):
    team = Team.query.get_or_404(team_id)
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

    # Teams exist karte hain?
    if not Team.query.get(data['team_a_id']):
        return jsonify({'message': 'Team A nahi mili'}), 404
    if not Team.query.get(data['team_b_id']):
        return jsonify({'message': 'Team B nahi mili'}), 404

    match = Match(
        title=data['title'],
        team_a_id=data['team_a_id'],
        team_b_id=data['team_b_id'],
        venue_id=data.get('venue_id'),
        organization_id=data.get('organization_id'),
        match_format=data.get('match_format', 'T20'),
        overs_per_innings=data.get('overs_per_innings', 20),
        scheduled_at=data.get('scheduled_at'),
        config=data.get('config', {}),
    )
    db.session.add(match)
    db.session.commit()
    return jsonify(match.to_dict()), 201


@matches_bp.route('/matches', methods=['GET'])
@jwt_required()
def list_matches():
    status = request.args.get('status')
    q = Match.query
    if status:
        q = q.filter_by(status=status)
    matches = q.order_by(Match.created_at.desc()).limit(50).all()
    return jsonify([m.to_dict() for m in matches])


@matches_bp.route('/matches/<int:match_id>', methods=['GET'])
@jwt_required()
def get_match(match_id):
    match = Match.query.get_or_404(match_id)
    d = match.to_dict()
    d['innings'] = [i.to_dict() for i in match.innings]
    return jsonify(d)


@matches_bp.route('/matches/<int:match_id>/toss', methods=['POST'])
@jwt_required()
def record_toss(match_id):
    match = Match.query.get_or_404(match_id)
    data = request.get_json() or {}
    winner_id = data.get('toss_winner_id')
    choice = data.get('toss_choice')  # bat/bowl

    if winner_id not in [match.team_a_id, match.team_b_id]:
        return jsonify({'message': 'Winner team match me nahi hai'}), 400
    if choice not in ['bat', 'bowl']:
        return jsonify({'message': 'Choice bat ya bowl hona chahiye'}), 400

    match.toss_winner_id = winner_id
    match.toss_choice = choice
    match.status = 'live'
    db.session.commit()
    return jsonify(match.to_dict())


@matches_bp.route('/matches/<int:match_id>/innings', methods=['POST'])
@jwt_required()
def start_innings(match_id):
    match = Match.query.get_or_404(match_id)
    data = request.get_json() or {}

    innings_num = len(match.innings) + 1
    if innings_num > 2:
        return jsonify({'message': '2 se zyada innings nahi!'}), 400

    batting_id = data.get('batting_team_id')
    if batting_id not in [match.team_a_id, match.team_b_id]:
        return jsonify({'message': 'Batting team match me nahi hai'}), 400

    bowling_id = match.team_b_id if batting_id == match.team_a_id else match.team_a_id

    innings = Innings(
        match_id=match.id,
        innings_number=innings_num,
        batting_team_id=batting_id,
        bowling_team_id=bowling_id,
        status='live',
    )
    db.session.add(innings)
    db.session.commit()
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
    innings = Innings.query.filter_by(id=innings_id,
                                      match_id=match_id).first_or_404()
    data = request.get_json() or {}

    try:
        # Delivery record banao
        from core_processing.scoring_engine import validate_delivery
        total_runs, is_legal = validate_delivery(
            runs_off_bat=data.get('runs_off_bat', 0),
            extras=data.get('extras', {}),
            is_wicket=data.get('is_wicket', False),
            wicket_type=data.get('wicket_type'),
        )
    except ScoringError as e:
        return jsonify({'message': f'Scoring error: {e}'}), 400

    # Ball number calculate karo
    last = Delivery.query.filter_by(innings_id=innings.id)\
                         .order_by(Delivery.ball_number.desc()).first()
    ball_number = (last.ball_number + 1) if last else 1

    # Legal balls gino (over calculation ke liye)
    legal_count = Delivery.query.filter_by(innings_id=innings.id,
                                           is_legal=True).count()
    over_number = legal_count // 6
    ball_in_over = (legal_count % 6) + 1 if is_legal else (legal_count % 6 or 6)

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

    # Innings totals update karo
    innings.total_runs += total_runs
    innings.total_balls += 1
    if is_legal:
        # legal balls se overs calculate
        legal_total = Delivery.query.filter_by(innings_id=innings.id,
                                               is_legal=True).count()
        innings.total_overs = legal_total // 6 + (legal_total % 6) / 10
    if delivery.is_wicket:
        innings.total_wickets += 1

    db.session.commit()

    return jsonify({
        'delivery': delivery.to_dict(),
        'innings': innings.to_dict(),
    }), 201


@matches_bp.route('/matches/<int:match_id>/scorecard', methods=['GET'])
@jwt_required()
def get_scorecard(match_id):
    """Poora match scorecard."""
    match = Match.query.get_or_404(match_id)
    result = match.to_dict()
    result['innings_detail'] = []
    for inn in match.innings:
        d = inn.to_dict()
        d['deliveries'] = [deliv.to_dict() for deliv in inn.deliveries]
        result['innings_detail'].append(d)
    return jsonify(result)

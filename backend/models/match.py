"""
StreetDRS Match Infrastructure — World-class database models.

Design principles (jaise top companies karti hain):
- Har entity ka clear ownership (org → venue → match → innings → delivery)
- Audit trail (kab bana, kab update hua)
- Soft relationships (ForeignKey + backref)
- JSON for flexible data (player stats, match config)
- to_dict() har model par (API serialization)

Modules covered: B (Organization/Venue), C (Match Management)
"""

from extensions import db
from datetime import datetime


class Organization(db.Model):
    """Academy, school, club, ya league."""
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    org_type = db.Column(db.String(30), default='club')  # academy/school/club/league
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    logo_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    venues = db.relationship('Venue', backref='organization', lazy=True,
                             cascade='all, delete-orphan')
    teams = db.relationship('Team', backref='organization', lazy=True,
                            cascade='all, delete-orphan')

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'org_type': self.org_type,
                'contact_email': self.contact_email,
                'created_at': self.created_at.isoformat() if self.created_at else None}


class Venue(db.Model):
    """Ground jahan match hota hai."""
    __tablename__ = 'venues'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(200))
    pitch_type = db.Column(db.String(30), default='turf')  # turf/matting/concrete
    # Camera calibration profile (reusable!)
    calibration_profile = db.Column(db.JSON)  # {cameras: [...], pitch_geometry: {...}}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'location': self.location,
                'pitch_type': self.pitch_type,
                'has_calibration': bool(self.calibration_profile)}


class Team(db.Model):
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    # Phase 1 (SEC-C3): creator/owner. Nullable only for legacy rows
    # created before this column existed; those rows are not writable
    # via the API (ownership filter requires an exact match).
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(10))  # "MI", "CSK"
    logo_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    players = db.relationship('Player', backref='team', lazy=True,
                              cascade='all, delete-orphan')

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'short_name': self.short_name,
                'player_count': len(self.players)}


class Player(db.Model):
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.Integer)
    batting_style = db.Column(db.String(20))  # RHB/LHB
    bowling_style = db.Column(db.String(30))  # RAFM/LAS etc.
    player_role = db.Column(db.String(20))  # batter/bowler/allrounder/wk
    photo_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {'id': self.id, 'name': self.name,
                'jersey_number': self.jersey_number,
                'batting_style': self.batting_style,
                'bowling_style': self.bowling_style,
                'player_role': self.player_role}


class Match(db.Model):
    """Ek cricket match — sab kuch isse judta hai."""
    __tablename__ = 'matches'

    id = db.Column(db.Integer, primary_key=True)
    # Phase 1 (SEC-C3): creator/owner — see Team.user_id note.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    venue_id = db.Column(db.Integer, db.ForeignKey('venues.id'))
    title = db.Column(db.String(200), nullable=False)  # "Final: Team A vs Team B"

    team_a_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    team_b_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)

    match_format = db.Column(db.String(20), default='T20')  # T20/ODI/Test/Custom
    overs_per_innings = db.Column(db.Integer, default=20)
    # Status: scheduled → live → completed (ya abandoned)
    status = db.Column(db.String(20), default='scheduled')

    # Toss
    toss_winner_id = db.Column(db.Integer, db.ForeignKey('teams.id'))
    toss_choice = db.Column(db.String(10))  # bat/bowl

    # Config (boundary, reviews allowed, etc.)
    config = db.Column(db.JSON, default=dict)

    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    innings = db.relationship('Innings', backref='match', lazy=True,
                              cascade='all, delete-orphan',
                              order_by='Innings.innings_number')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title,
            # BE-M4: venue/organization ids pehle gayab the.
            'venue_id': self.venue_id, 'organization_id': self.organization_id,
            'team_a_id': self.team_a_id, 'team_b_id': self.team_b_id,
            'match_format': self.match_format,
            'overs_per_innings': self.overs_per_innings,
            'status': self.status,
            'toss_winner_id': self.toss_winner_id,
            'toss_choice': self.toss_choice,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'innings_count': len(self.innings),
        }


class Innings(db.Model):
    """Ek innings — ek team ki batting."""
    __tablename__ = 'innings'

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    innings_number = db.Column(db.Integer, nullable=False)  # 1 ya 2
    batting_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    bowling_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)

    # Live score (har ball par update hota hai)
    total_runs = db.Column(db.Integer, default=0)
    total_wickets = db.Column(db.Integer, default=0)
    total_overs = db.Column(db.Float, default=0.0)  # 4.3 = 4 overs 3 balls
    # BE-H5: total_balls = SAB deliveries (wide/no-ball samet); legal
    # balls ka alag count total_legal_balls me. Pehle total_balls har
    # ball par badhta tha lekin comment "legal balls" kehta tha, aur
    # run rate total_balls se nikalta tha jabki total_overs legal-only
    # tha — dono disagree karte the.
    total_balls = db.Column(db.Integer, default=0)  # all deliveries
    total_legal_balls = db.Column(db.Integer, default=0)  # legal only

    status = db.Column(db.String(20), default='not_started')  # live/completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deliveries = db.relationship('Delivery', backref='innings', lazy=True,
                                 cascade='all, delete-orphan',
                                 order_by='Delivery.ball_number')

    def to_dict(self):
        # Run rate hamesha LEGAL balls se (BE-H5): wides/no-balls ke
        # baad bhi total_overs aur run rate ek-doosre se agree karenge.
        # Legacy rows (total_legal_balls NULL) par total_balls fallback.
        legal = (self.total_legal_balls if self.total_legal_balls is not None
                 else self.total_balls)
        return {
            'id': self.id, 'innings_number': self.innings_number,
            'batting_team_id': self.batting_team_id,
            'total_runs': self.total_runs, 'total_wickets': self.total_wickets,
            'total_overs': self.total_overs, 'total_balls': self.total_balls,
            'total_legal_balls': legal,
            'status': self.status,
            'run_rate': round(self.total_runs / (legal / 6), 2)
                        if legal > 0 else 0,
        }


class Delivery(db.Model):
    """
    Ek ball — sabse granular level.
    Har ball ka poora record: score, bowler, batsmen, extras, DRS link.
    """
    __tablename__ = 'deliveries'

    id = db.Column(db.Integer, primary_key=True)
    innings_id = db.Column(db.Integer, db.ForeignKey('innings.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)

    # Ball identification
    over_number = db.Column(db.Integer, nullable=False)  # 0-indexed
    ball_number = db.Column(db.Integer, nullable=False)  # overall ball count
    ball_in_over = db.Column(db.Integer, nullable=False)  # 1-6 (legal balls)

    # Players
    bowler_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    striker_id = db.Column(db.Integer, db.ForeignKey('players.id'))
    non_striker_id = db.Column(db.Integer, db.ForeignKey('players.id'))

    # Score
    runs_off_bat = db.Column(db.Integer, default=0)  # 0-6
    extras = db.Column(db.JSON, default=dict)  # {wide: 1, noball: 0, bye: 0, legbye: 0}
    total_runs = db.Column(db.Integer, default=0)  # runs_off_bat + extras

    # Wicket
    is_wicket = db.Column(db.Boolean, default=False)
    wicket_type = db.Column(db.String(30))  # bowled/caught/lbw/runout/stumped/hitwicket
    out_player_id = db.Column(db.Integer, db.ForeignKey('players.id'))

    # Ball tracking link (AI analysis)
    tracking_data = db.Column(db.JSON)  # trajectory, speed, pitch point, etc.
    review_id = db.Column(db.Integer, db.ForeignKey('reviews.id'))  # DRS review link

    is_legal = db.Column(db.Boolean, default=True)  # wide/noball = illegal
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            # BE-M4: pehle innings_id/match_id/ball_number/non_striker/
            # out_player/review_id gayab the — additive fields hain.
            'id': self.id, 'innings_id': self.innings_id,
            'match_id': self.match_id,
            'over_number': self.over_number,
            'ball_number': self.ball_number,
            'ball_in_over': self.ball_in_over,
            'bowler_id': self.bowler_id, 'striker_id': self.striker_id,
            'non_striker_id': self.non_striker_id,
            'runs_off_bat': self.runs_off_bat, 'extras': self.extras,
            'total_runs': self.total_runs,
            'is_wicket': self.is_wicket, 'wicket_type': self.wicket_type,
            'out_player_id': self.out_player_id,
            'review_id': self.review_id,
            'is_legal': self.is_legal,
        }

"""
AI Coach Full — StreetDRS spec module T (poora karo).

T4. Goal setting: target accuracy, session volume
T5. Progress tracking: sessions compare karo
T6. Drill recommendations: weakness par drills
"""

from extensions import db
from datetime import datetime


class TrainingGoal(db.Model):
    """T4: Player ka goal."""
    __tablename__ = 'training_goals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'))

    goal_type = db.Column(db.String(30), nullable=False)
    # accuracy_pct / avg_speed / good_length_pct / sessions_per_week
    target_value = db.Column(db.Float, nullable=False)
    current_value = db.Column(db.Float)
    deadline = db.Column(db.DateTime)

    status = db.Column(db.String(20), default='active')  # active/achieved/paused
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        progress = None
        if self.current_value is not None and self.target_value:
            progress = round(min(100, self.current_value / self.target_value * 100), 1)
        return {
            'id': self.id, 'goal_type': self.goal_type,
            'target_value': self.target_value,
            'current_value': self.current_value,
            'progress_pct': progress, 'status': self.status,
        }


# T6: Drill library — weakness → drill
DRILLS = {
    'accuracy': [
        {'name': 'Target Bowling', 'desc': 'Cone rakho good length par, 30 balls target par daalo. Goal: 70%+ accuracy.'},
        {'name': 'Single Stump', 'desc': 'Sirf ek stump ko nishana banao, 20 balls. Line control ke liye.'},
    ],
    'pace': [
        {'name': 'Run-up Rhythm', 'desc': 'Run-up ki speed badhao, 10 balls full effort. Speed gun se measure karo.'},
        {'name': 'Wrist Position', 'desc': 'Wrist cocked rakho release par, 20 balls shadow bowling.'},
    ],
    'consistency': [
        {'name': '6-Ball Sets', 'desc': '6 balls ek hi length par — 5 sets. Har set me 4+ good length chahiye.'},
        {'name': 'Blind Target', 'desc': 'Bina dekhe feel se bowling — muscle memory ke liye.'},
    ],
    'variation': [
        {'name': 'Slower Ball Practice', 'desc': '10 slower balls, 10 normal — batsman ko confuse karo.'},
        {'name': 'Yorker Challenge', 'desc': 'Lagatar 12 yorkers — death bowling ke liye.'},
    ],
}


def recommend_drills(weaknesses):
    """
    T6: Weakness list se drills suggest karo.
    weaknesses: ['accuracy', 'pace'] etc.
    """
    drills = []
    for w in weaknesses:
        if w in DRILLS:
            for d in DRILLS[w]:
                drills.append({'weakness': w, **d})
    return drills


def detect_weaknesses(report):
    """
    Training report se weaknesses nikalo.
    report: session_report() ka output
    Returns: ['accuracy', 'pace', ...]
    """
    weaknesses = []
    bowling = report.get('bowling', {})

    acc = bowling.get('target_accuracy_pct', 100)
    if acc < 60:
        weaknesses.append('accuracy')

    avg_speed = bowling.get('avg_speed')
    if avg_speed and avg_speed < 120:
        weaknesses.append('pace')

    lengths = bowling.get('length_distribution', {})
    total = sum(lengths.values()) or 1
    good_pct = lengths.get('Good length', 0) / total * 100
    if good_pct < 50:
        weaknesses.append('consistency')

    return weaknesses


def compare_sessions(reports):
    """
    T5: Multiple sessions compare karo — progress dikhao.
    reports: [session_report(), ...] chronological
    """
    if len(reports) < 2:
        return {'message': 'Compare ke liye 2+ sessions chahiye'}

    first = reports[0]['bowling']
    last = reports[-1]['bowling']

    def _diff(key):
        a, b = first.get(key), last.get(key)
        if a is None or b is None:
            return None
        return round(b - a, 1)

    return {
        'sessions_compared': len(reports),
        'avg_speed_change': _diff('avg_speed'),
        'accuracy_change': _diff('target_accuracy_pct'),
        'trend': 'improving' if (_diff('target_accuracy_pct') or 0) > 0 else 'needs_work',
    }

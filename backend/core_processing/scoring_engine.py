"""
StreetDRS Scoring Engine — World-class cricket scoring logic.

Design (jaise Cricinfo/ESPNcricinfo ka backend):
- Har ball ek event hai — scoring engine state update karta hai
- Validation: galat score enter nahi ho sakta (7 runs off bat impossible!)
- Derived stats: strike rate, economy, partnerships, run rate
- Audit: har change ka history

Cricket rules (simplified but correct):
- Wide: 1 run extra (+ additional runs), ball not counted
- No-ball: 1 run extra (+ bat runs), ball not counted
- Bye/Leg-bye: extras, ball counted
- Wicket: ball counted (except run-out on wide/noball — complex, simplified)
- Max 6 runs off bat (7+ with overthrows possible but rare — allow up to 8)
"""

VALID_WICKET_TYPES = {
    'bowled', 'caught', 'lbw', 'runout', 'stumped',
    'hitwicket', 'retired', 'obstructing',
}

VALID_EXTRAS = {'wide', 'noball', 'bye', 'legbye', 'penalty'}


class ScoringError(Exception):
    """Galat scoring attempt."""
    pass


def validate_delivery(runs_off_bat=0, extras=None, is_wicket=False,
                      wicket_type=None):
    """
    Ball ko validate karo — galat data reject karo.
    Returns: (total_runs, is_legal)
    Raises: ScoringError agar invalid
    """
    extras = extras or {}

    # Runs validation
    if not 0 <= runs_off_bat <= 8:
        raise ScoringError(f"runs_off_bat {runs_off_bat} invalid (0-8)")

    # Extras validation
    for k, v in extras.items():
        if k not in VALID_EXTRAS:
            raise ScoringError(f"Unknown extra type: {k}")
        if not 0 <= v <= 6:
            raise ScoringError(f"Extra {k}={v} invalid")

    # Wide + runs off bat nahi ho sakta (wide par bat se run nahi)
    if extras.get('wide', 0) > 0 and runs_off_bat > 0:
        raise ScoringError("Wide par bat se run nahi ho sakta")

    # Bat runs + bye/leg-bye ek saath impossible (overthrows unmodelled)
    if runs_off_bat > 0 and (extras.get('bye', 0) > 0
                             or extras.get('legbye', 0) > 0):
        raise ScoringError("Bat runs aur bye/leg-bye ek saath nahi ho sakte")

    # Wide + bye/leg-bye ek saath — wahi runs do baar ginne jaate
    if extras.get('wide', 0) > 0 and (extras.get('bye', 0) > 0
                                      or extras.get('legbye', 0) > 0):
        raise ScoringError("Wide par bye/leg-bye alag se nahi ho sakte")

    # Bye aur leg-bye ek saath impossible — ek ball ek hi tarah ka extra
    if extras.get('bye', 0) > 0 and extras.get('legbye', 0) > 0:
        raise ScoringError("Bye aur leg-bye ek saath nahi ho sakte")

    # Penalty hamesha 5 runs hoti hai (BE-H4: up to 6 allow karna galat)
    if extras.get('penalty', 0) not in (0, 5):
        raise ScoringError("Penalty hamesha 5 runs hoti hai")

    # Wicket ke saath bat runs: sirf run-out par completed runs ho sakte
    # hain — bowled/caught/lbw/stumped/hitwicket/retired/obstructing
    # par bat se run impossible hai.
    if is_wicket and runs_off_bat > 0 and wicket_type != 'runout':
        raise ScoringError(
            "Wicket ke saath bat runs sirf run-out par ho sakte hain")

    # No-ball par wicket nahi (except runout)
    if extras.get('noball', 0) > 0 and is_wicket:
        if wicket_type != 'runout':
            raise ScoringError("No-ball par sirf run-out ho sakta hai")

    # Wicket type validation
    if is_wicket and wicket_type not in VALID_WICKET_TYPES:
        raise ScoringError(f"Invalid wicket type: {wicket_type}")
    if not is_wicket and wicket_type:
        raise ScoringError("Wicket nahi to wicket_type kyun?")

    # Legal ball?
    is_legal = not (extras.get('wide', 0) > 0 or extras.get('noball', 0) > 0)

    total_runs = runs_off_bat + sum(extras.values())
    return total_runs, is_legal


class InningsState:
    """
    Ek innings ka live state — har ball par update hota hai.
    Ye pure Python hai (DB se independent) — testing easy!
    """

    def __init__(self, max_overs=20, max_wickets=10):
        self.max_overs = max_overs
        self.max_wickets = max_wickets
        self.max_balls = max_overs * 6

        self.runs = 0
        self.wickets = 0
        self.legal_balls = 0
        self.total_balls = 0  # including wides/noballs

        # Batter stats: {player_id: {runs, balls, fours, sixes}}
        self.batters = {}
        # Bowler stats: {player_id: {balls, runs, wickets, wides, noballs}}
        self.bowlers = {}

        self.current_striker = None
        self.current_non_striker = None
        self.current_bowler = None

        # Partnership
        self.partnership_runs = 0
        self.partnership_balls = 0

        # Over history: [(over_num, runs, wickets), ...]
        self.overs = []
        self._current_over_runs = 0
        self._current_over_wkts = 0

        # Fall of wickets: [(runs, over, player_id), ...]
        self.fall_of_wickets = []

    def set_batters(self, striker_id, non_striker_id):
        self.current_striker = striker_id
        self.current_non_striker = non_striker_id
        for pid in [striker_id, non_striker_id]:
            if pid not in self.batters:
                self.batters[pid] = {'runs': 0, 'balls': 0,
                                     'fours': 0, 'sixes': 0, 'out': False}

    def set_bowler(self, bowler_id):
        self.current_bowler = bowler_id
        if bowler_id not in self.bowlers:
            self.bowlers[bowler_id] = {'balls': 0, 'runs': 0, 'wickets': 0,
                                       'wides': 0, 'noballs': 0, 'dots': 0}

    def add_ball(self, runs_off_bat=0, extras=None, is_wicket=False,
                 wicket_type=None, out_player_id=None):
        """
        Ek ball add karo. Sab kuch auto-update!
        Returns: ball summary dict
        """
        extras = extras or {}
        total_runs, is_legal = validate_delivery(
            runs_off_bat, extras, is_wicket, wicket_type)

        if self.is_innings_over():
            raise ScoringError("Innings khatam ho gayi!")

        # --- Update totals ---
        self.runs += total_runs
        self.total_balls += 1
        if is_legal:
            self.legal_balls += 1

        # --- Batter stats ---
        # BE-H4: no-ball par bat runs batter ko milte hain (ball count
        # nahi hoti, runs hote hain) — pehle is_legal gate se ye runs
        # gayab ho jaate the jabki bowler ke runs me jud jaate the.
        striker = self.batters.get(self.current_striker)
        if striker:
            if is_legal:
                striker['balls'] += 1
            striker['runs'] += runs_off_bat
            if runs_off_bat == 4:
                striker['fours'] += 1
            elif runs_off_bat == 6:
                striker['sixes'] += 1

        # --- Bowler stats ---
        bowler = self.bowlers.get(self.current_bowler)
        if bowler:
            if is_legal:
                bowler['balls'] += 1
            bowler['runs'] += total_runs
            # Wides/noballs bowler ke khate me
            bowler['wides'] += extras.get('wide', 0)
            bowler['noballs'] += extras.get('noball', 0)
            if total_runs == 0 and is_legal:
                bowler['dots'] += 1
            # BE-H4: bowler ka wicket sirf bowler's wickets par —
            # retired / obstructing (aur run-out) bowler ke khate me nahi.
            if is_wicket and wicket_type in {
                    'bowled', 'caught', 'lbw', 'stumped', 'hitwicket'}:
                bowler['wickets'] += 1

        # --- Wicket ---
        if is_wicket:
            self.wickets += 1
            out_id = out_player_id or self.current_striker
            if out_id in self.batters:
                self.batters[out_id]['out'] = True
            over_str = f"{self.legal_balls // 6}.{self.legal_balls % 6}"
            self.fall_of_wickets.append((self.runs, over_str, out_id))
            # Partnership reset
            self.partnership_runs = 0
            self.partnership_balls = 0
        else:
            self.partnership_runs += total_runs
            if is_legal:
                self.partnership_balls += 1

        # --- Over tracking ---
        self._current_over_runs += total_runs
        if is_wicket:
            self._current_over_wkts += 1

        # Over complete?
        over_completed = False
        if self.legal_balls % 6 == 0 and self.legal_balls > 0:
            over_num = self.legal_balls // 6
            self.overs.append((over_num, self._current_over_runs,
                               self._current_over_wkts))
            self._current_over_runs = 0
            self._current_over_wkts = 0
            over_completed = True
            # Strike change (over ke baad)
            self.current_striker, self.current_non_striker = \
                self.current_non_striker, self.current_striker

        # Strike change (odd runs par)
        if total_runs % 2 == 1:
            self.current_striker, self.current_non_striker = \
                self.current_non_striker, self.current_striker

        return {
            'runs': self.runs, 'wickets': self.wickets,
            'overs': self.get_overs_str(),
            'total_runs_this_ball': total_runs,
            'is_legal': is_legal,
            'over_completed': over_completed,
            'striker': self.current_striker,
        }

    def get_overs_str(self):
        """'4.3' format me overs."""
        return f"{self.legal_balls // 6}.{self.legal_balls % 6}"

    def get_run_rate(self):
        if self.legal_balls == 0:
            return 0.0
        return round(self.runs / (self.legal_balls / 6), 2)

    def is_innings_over(self):
        return (self.wickets >= self.max_wickets or
                self.legal_balls >= self.max_balls)

    def get_scorecard(self):
        """Poora scorecard."""
        batting = []
        for pid, s in self.batters.items():
            sr = round(s['runs'] / s['balls'] * 100, 1) if s['balls'] > 0 else 0
            batting.append({'player_id': pid, **s, 'strike_rate': sr})

        bowling = []
        for pid, s in self.bowlers.items():
            overs = f"{s['balls'] // 6}.{s['balls'] % 6}"
            econ = round(s['runs'] / (s['balls'] / 6), 2) if s['balls'] > 0 else 0
            bowling.append({'player_id': pid, 'overs': overs,
                            'economy': econ, **s})

        return {
            'runs': self.runs, 'wickets': self.wickets,
            'overs': self.get_overs_str(), 'run_rate': self.get_run_rate(),
            'batting': batting, 'bowling': bowling,
            'partnership': {'runs': self.partnership_runs,
                            'balls': self.partnership_balls},
            'fall_of_wickets': self.fall_of_wickets,
            'is_over': self.is_innings_over(),
        }

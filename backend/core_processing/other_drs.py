"""
Other DRS Decision Engines — StreetDRS spec module M.

M1. Run-out: ball vs bat-ground position at wicket-break time
M2. Stumping: keeper breaks wicket, batter out of crease?
M3. Wide: ball passes outside wide guidelines
M4. No-ball: front foot over crease, height violations

Sab engines evidence-based hain — INCONCLUSIVE return karte hain
jab evidence insufficient ho (spec ka rule!).

Usage:
    from core_processing.other_drs import RunOutEngine, WideEngine
    engine = RunOutEngine()
    result = engine.analyze(
        ball_positions=[...],      # [(x, y, frame), ...]
        bat_positions=[...],       # batsman/bat foot position
        crease_x=100,              # crease line x-coordinate (pixels)
        wicket_break_frame=45,     # jab bail giri
    )
    # → {'decision': 'OUT'|'NOT OUT'|'INCONCLUSIVE', 'confidence': ..., 'evidence': {...}}
"""

import math


class BaseEngine:
    """Sab engines ka base — common helpers."""

    @staticmethod
    def _interpolate(positions, target_frame):
        """Frame ke liye position interpolate karo."""
        if not positions:
            return None
        # positions: [(x, y, frame), ...] sorted by frame
        for i in range(len(positions) - 1):
            f0 = positions[i][2]
            f1 = positions[i + 1][2]
            if f0 <= target_frame <= f1:
                if f1 == f0:
                    return positions[i][:2]
                t = (target_frame - f0) / (f1 - f0)
                x = positions[i][0] + t * (positions[i+1][0] - positions[i][0])
                y = positions[i][1] + t * (positions[i+1][1] - positions[i][1])
                return (x, y)
        # Bahar ho to nearest
        if target_frame < positions[0][2]:
            return positions[0][:2]
        return positions[-1][:2]

    @staticmethod
    def _result(decision, confidence, evidence, reasoning):
        return {
            'decision': decision,
            'confidence': round(confidence, 1),
            'evidence': evidence,
            'reasoning': reasoning,
        }


class RunOutEngine(BaseEngine):
    """
    M1. Run-out detection.

    Logic:
    1. Wicket break hone ke time par ball kahan thi?
    2. Batsman ka bat/ground crease ke andar tha ya bahar?
    3. Agar bahar → OUT, andar → NOT OUT
    """

    def analyze(self, bat_positions, crease_x, wicket_break_frame,
                ball_positions=None):
        """
        bat_positions: [(x, y, frame), ...] — bat ka toe ya foot
        crease_x: popping crease ka x (pixels)
        wicket_break_frame: bail kab giri
        """
        if not bat_positions:
            return self._result('INCONCLUSIVE', 0, {},
                                'Batsman position data nahi mila')

        bat_at_break = self._interpolate(bat_positions, wicket_break_frame)
        if bat_at_break is None:
            return self._result('INCONCLUSIVE', 0, {},
                                'Break time par position nahi mili')

        bat_x = bat_at_break[0]
        # Crease ke piche (x < crease_x) = safe, aage = out
        # (Assume: batsman left se right bhag raha hai, crease vertical line)
        is_grounded = bat_x < crease_x
        distance_px = abs(bat_x - crease_x)

        evidence = {
            'bat_x_at_break': round(bat_x, 1),
            'crease_x': crease_x,
            'distance_from_crease_px': round(distance_px, 1),
            'wicket_break_frame': wicket_break_frame,
        }

        # Confidence: jitna door, utna confident
        confidence = min(95, 50 + distance_px / 2)

        if is_grounded:
            return self._result('NOT OUT', confidence, evidence,
                                f'Bat crease ke {distance_px:.0f}px piche tha — grounded!')
        else:
            return self._result('OUT', confidence, evidence,
                                f'Bat crease se {distance_px:.0f}px bahar tha — run out!')


class StumpingEngine(BaseEngine):
    """
    M2. Stumping detection.

    Logic: Keeper ne wicket todi, tab batsman crease me tha ya nahi?
    + Kya ball wide/stumping ke liye valid thi?
    """

    def analyze(self, batter_foot_positions, crease_x, wicket_break_frame,
                is_wide=False):
        if is_wide:
            # Wide par stumping nahi ho sakta (stumping sirf valid ball par)
            # Actually wide par stumping HO SAKTA hai! Correction:
            pass

        foot_at_break = self._interpolate(batter_foot_positions,
                                          wicket_break_frame)
        if foot_at_break is None:
            return self._result('INCONCLUSIVE', 0, {},
                                'Batter foot position nahi mili')

        foot_x = foot_at_break[0]
        is_grounded = foot_x < crease_x
        distance_px = abs(foot_x - crease_x)

        evidence = {
            'foot_x_at_break': round(foot_x, 1),
            'crease_x': crease_x,
            'distance_from_crease_px': round(distance_px, 1),
        }
        confidence = min(95, 50 + distance_px / 2)

        if is_grounded:
            return self._result('NOT OUT', confidence, evidence,
                                'Batter crease me tha — not stumped!')
        return self._result('OUT', confidence, evidence,
                            f'Batter {distance_px:.0f}px bahar — STUMPED!')


class WideEngine(BaseEngine):
    """
    M3. Wide ball detection.

    Logic: Ball jab batsman ke paas se guzri, tab wide guideline se bahar thi?
    """

    def __init__(self, wide_line_offset_px=50):
        # Wide guideline: off stump se kitne pixels bahar
        self.wide_offset = wide_line_offset_px

    def analyze(self, ball_positions, stump_x, batter_moved=False):
        """
        ball_positions: [(x, y, frame), ...]
        stump_x: off stump ka x
        batter_moved: agar batsman hila to wide nahi (uncertain)
        """
        if batter_moved:
            return self._result('INCONCLUSIVE', 0, {},
                                'Batsman hila tha — wide uncertain')

        if not ball_positions or len(ball_positions) < 3:
            return self._result('INCONCLUSIVE', 0, {},
                                'Ball trajectory incomplete')

        # Ball ka max lateral deviation nikalo (batsman ke paas)
        # Simple: last few positions ka x dekho
        recent = ball_positions[-5:]
        max_x = max(p[0] for p in recent)
        wide_line = stump_x + self.wide_offset

        evidence = {
            'max_ball_x': round(max_x, 1),
            'wide_line_x': wide_line,
            'deviation_px': round(max_x - stump_x, 1),
        }

        if max_x > wide_line:
            confidence = min(95, 60 + (max_x - wide_line) / 2)
            return self._result('WIDE', confidence, evidence,
                                f'Ball wide line se {(max_x-wide_line):.0f}px bahar!')
        else:
            confidence = min(95, 60 + (wide_line - max_x) / 2)
            return self._result('NOT WIDE', confidence, evidence,
                                'Ball wide line ke andar thi.')


class NoBallEngine(BaseEngine):
    """
    M4. No-ball detection.

    - Front foot: bowler ka foot crease se aage?
    - Height: waist se upar full toss? (batsman reference chahiye)
    """

    def check_front_foot(self, foot_x, crease_x):
        """Front foot no-ball: foot crease line se aage?"""
        is_over = foot_x > crease_x
        distance = abs(foot_x - crease_x)
        evidence = {
            'foot_x': round(foot_x, 1),
            'crease_x': crease_x,
            'overstep_px': round(distance, 1) if is_over else 0,
        }
        if is_over:
            confidence = min(98, 70 + distance)
            return self._result('NO BALL', confidence, evidence,
                                f'Front foot {distance:.0f}px aage — NO BALL!')
        return self._result('LEGAL', min(95, 70 + distance), evidence,
                            'Front foot crease ke piche.')

    def check_height(self, ball_height_px, waist_height_px):
        """Waist-high full toss check."""
        if ball_height_px is None or waist_height_px is None:
            return self._result('INCONCLUSIVE', 0, {},
                                'Height reference nahi mila')
        # Note: y-axis me upar = kam value (image coordinates)
        is_high = ball_height_px < waist_height_px
        evidence = {
            'ball_y': round(ball_height_px, 1),
            'waist_y': round(waist_height_px, 1),
        }
        if is_high:
            return self._result('NO BALL', 85, evidence,
                                'Waist se upar full toss — NO BALL!')
        return self._result('LEGAL', 85, evidence, 'Height theek hai.')

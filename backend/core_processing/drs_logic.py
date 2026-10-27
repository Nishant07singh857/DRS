"""
DRS LBW Decision — ICC Playing Conditions ka EXACT protocol.

International cricket me third umpire isi order me check karta hai:

  Step 1: NO-BALL? → hai to seedha NOT OUT
  Step 2: PITCHING — kahan pitch hui? (BOUNCE point, release point nahi)
  Step 3: BAT involved? → pehle bat laga to NOT OUT (BE-L1: header ab
    code order se match karta hai — pehle header me Step 3/4 ulte the)
  Step 4: IMPACT — kahan lagi?
  Step 5: WICKETS HITTING — Hawk-Eye projection (pre-impact segment se)
  Step 6: UMPIRE'S CALL — marginal par on-field decision

ICC Law 36 (LBW) ke key rules:
- Leg stump ke bahar pitch → hamesha NOT OUT
- Shot khel raha hai to: pitching + impact dono line me hone chahiye
- Shot NAHI khel raha to: impact bahar bhi chalega (pitching phir bhi leg ke bahar nahi,
  aur impact leg stump ke bahar kabhi nahi — no-shot exception sirf off side ke liye hai)
- Umpire's Call: pitching/impact/hitting me se koi bhi <50% ball-overlap
  to on-field umpire ka faisla rehta hai

Phase 3 (BE-C1/BE-H1/BE-H2/BE-H3/BE-H9) fixes vs. the old code:
- BE-C1: pitch point = trajectory[detect_bounce(trajectory)], NOT
  trajectory[0] (release / earliest tracked frame). No bounce detected
  → INCONCLUSIVE (a full toss / yorker whose bounce was never tracked
  needs separate handling; it must not be judged off the release point).
- BE-H1: hitting is extrapolated from the PRE-IMPACT segment (the live
  trajectory's last point is the pad-impact point, so its direction
  includes pad deflection), checked in x WITH ball radius and in y
  against stump height (0.711 m), and the path is bounded in y (below
  the ground / out of frame stops it). A ball flying OVER the stumps
  no longer counts as HITTING.
- BE-H2: the UMPIRE_CALL_*_MARGIN = 0.5 constants are now actually
  applied, to real pitch/impact/hitting ball-overlap fractions — the
  old "confidence = 50 + 35*R^2 + length bonus" from the linearity of
  the last 8 points is gone. on_field_call is validated.
- BE-H3: impact beyond the leg stump is rejected regardless of shot.
- BE-H9: pitch_in_line / impact_in_line / hitting_wickets are computed
  from the actual step results (in-line vs outside-off vs outside-leg,
  real impact, real hitting), not from step passes / hardcoded True /
  (final_decision == 'OUT').

Calibration note: stump height / ball radius in pixels default to the
same uncalibrated broadcast-andaza scale ball_physics uses
(50 px/m → stump 35.6 px, ball radius 1.8 px). A calibrated caller
passes stump_height_px (e.g. from the calibration API's stump height
in px) and ball_radius_px; the result is then a calibrated hitting
check. The ground line for the stump band is the bounce point's y
(the ball's ground contact), falling back to the trajectory's max y.
"""

try:
    from core_processing.ball_physics import detect_bounce
except ImportError:  # core_processing dir khud sys.path par ho to
    from ball_physics import detect_bounce

# Umpire's Call thresholds (ICC: 50% of ball must be hitting)
UMPIRE_CALL_PITCH_MARGIN = 0.5   # ball ka kitna hissa line me
UMPIRE_CALL_IMPACT_MARGIN = 0.5
UMPIRE_CALL_HITTING_MARGIN = 0.5

# Uncalibrated pixel scale (ball_physics default: 50 px/m). Only used
# when the caller passes no calibrated stump height / ball radius.
_DEFAULT_PX_PER_M = 50.0
STUMP_HEIGHT_M = 0.711
BALL_RADIUS_M = 0.036


def _overlap_fraction(centre, radius, zone):
    """Ball interval [centre-radius, centre+radius] ka kitna hissa
    stumps zone ke andar hai, ball diameter ke fraction me (0.0-1.0)."""
    lo = max(centre - radius, zone[0])
    hi = min(centre + radius, zone[1])
    overlap = max(0.0, hi - lo)
    return overlap / (2.0 * radius) if radius > 0 else 0.0


def _predict_path(trajectory, stumps_zone, frame_width, frame_height=None,
                  ground_y=None, stump_height_px=None, ball_radius_px=None,
                  max_steps=300):
    """Ball ka rasta aage badhao — hitting check karo.

    trajectory: PRE-IMPACT segment (caller slices off the impact point;
    extrapolating from the impact point would bake pad deflection into
    the direction). Returns (hitting, path, hitting_overlap):
    hitting = the extrapolated ball interval overlaps the stumps zone
    at a step whose y lies within the stump band
    [ground_y - stump_height, ground_y] (plus ball radius); a ball
    flying OVER the stumps (y above the band) is MISSING, not HITTING.
    The path stops at the frame's x/y bounds or below the ground, so a
    near-vertical trajectory cannot spin out ~300 near-constant-x points
    past the stumps. hitting_overlap is the ball-overlap fraction at
    the first hitting step (for the ICC 50% Umpire's Call test).
    """
    if len(trajectory) < 2:
        return False, [], 0.0
    if stump_height_px is None:
        stump_height_px = STUMP_HEIGHT_M * _DEFAULT_PX_PER_M
    if ball_radius_px is None:
        ball_radius_px = BALL_RADIUS_M * _DEFAULT_PX_PER_M
    if ground_y is None:
        ground_y = max(p[1] for p in trajectory)
    stump_top = ground_y - stump_height_px

    (x1, y1), (x2, y2) = trajectory[-2], trajectory[-1]
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return False, []
    length = (dx ** 2 + dy ** 2) ** 0.5
    step_x, step_y = dx / length * 4.0, dy / length * 4.0
    px, py = float(x2), float(y2)
    path = []
    for _ in range(max_steps):
        px += step_x
        py += step_y
        if not (0 < px < frame_width):
            break
        if frame_height is not None and not (0 <= py <= frame_height):
            break
        if py > ground_y + ball_radius_px:
            break  # ground ke neeche — ball ruk gayi / stumps ke paar
        path.append([round(px, 1), round(py, 1)])
        if stump_top - ball_radius_px <= py <= ground_y + ball_radius_px:
            overlap = _overlap_fraction(px, ball_radius_px, stumps_zone)
            if overlap > 0:
                return True, path, round(overlap, 3)
    return False, path, 0.0


def analyze_lbw_icc(tracking_data, frame_width, frame_height=None,
                    is_no_ball=False, playing_shot=True,
                    bat_involved=False, on_field_call='OUT',
                    stumps_zone=None, leg_side_x=None, fps=30,
                    handedness='RHB', stump_height_px=None,
                    ball_radius_px=None):
    # fps: EFFECTIVE fps of the trajectory points (CV-C5). tasks.py
    # passes video_fps / TRACK_EVERY_N_FRAMES; the old hardcoded 30
    # overstated speed ~2x at the default 2x sampling. Default 30
    # preserves the old behaviour for direct callers.
    """
    ICC protocol ke hisab se LBW decision.

    Args:
        tracking_data: {"ball": (x,y), "trajectory": [(x,y),...]}
        frame_width/height: frame dimensions
        is_no_ball: front-foot no-ball thi?
        playing_shot: batsman shot khel raha tha?
        bat_involved: UltraEdge ne bat-ball contact detect kiya?
        on_field_call: 'OUT' ya 'NOT OUT' (umpire's call ke liye) —
            koi aur value ValueError deti hai (BE-H2).
        stumps_zone: (x1, x2) — calibrate kiya hua, warna auto
        leg_side_x: leg side ka threshold (RHB convention), warna auto
        handedness: 'RHB' (leg side x > leg_side_x) ya 'LHB' (leg side
            mirrored: x < frame_width - leg_side_x). Koi aur value
            ValueError deti hai.
        stump_height_px / ball_radius_px: calibrated pixel scale for
            the hitting check; uncalibrated defaults (50 px/m) apply
            when omitted — see module docstring.

    Returns: full decision with step-by-step reasoning (jaise TV par dikhta hai!)
    """
    trajectory = tracking_data.get("trajectory") or []
    ball_pos = tracking_data.get("ball")

    steps = []  # Har step ka result (TV graphic ke liye!)

    if not ball_pos or len(trajectory) < 3:
        return None

    if on_field_call not in ('OUT', 'NOT OUT'):
        raise ValueError(
            f"on_field_call 'OUT' ya 'NOT OUT' hona chahiye, mila: {on_field_call!r}")
    if handedness not in ('RHB', 'LHB'):
        raise ValueError(
            f"handedness 'RHB' ya 'LHB' hona chahiye, mila: {handedness!r}")

    # Zones
    if stumps_zone is None:
        stumps_zone = (frame_width * 0.4, frame_width * 0.6)
    if leg_side_x is None:
        leg_side_x = frame_width * 0.7  # RHB ke liye
    # LHB: leg side mirror hoti hai.
    leg_threshold = leg_side_x if handedness == 'RHB' else frame_width - leg_side_x

    def _outside_leg(x):
        return x > leg_threshold if handedness == 'RHB' else x < leg_threshold

    if ball_radius_px is None:
        ball_radius_px = BALL_RADIUS_M * _DEFAULT_PX_PER_M

    # ===== STEP 1: NO-BALL =====
    if is_no_ball:
        steps.append({'step': 1, 'check': 'No-ball',
                      'result': 'NO BALL — NOT OUT', 'pass': False})
        return _final('NOT OUT', 100, steps, trajectory, ball_pos,
                      frame_width, frame_height, None,
                      stumps_zone, fps=fps, reason='No-ball par LBW nahi ho sakta')
    steps.append({'step': 1, 'check': 'No-ball',
                  'result': 'Fair delivery', 'pass': True})

    # ===== STEP 2: PITCHING (BE-C1: bounce point, not release) =====
    bounce_idx = detect_bounce(trajectory)
    if bounce_idx is None:
        # Bounce dikhi hi nahi — full toss, ya bounce track hi nahi hui.
        # trajectory[0] (release) se pitch judge karna galat hoga, isliye
        # decision INCONCLUSIVE: is delivery ka alag handling chahiye.
        steps.append({'step': 2, 'check': 'Pitching',
                      'result': 'NO BOUNCE DETECTED — INCONCLUSIVE',
                      'pass': False})
        return _final('INCONCLUSIVE', 50, steps, trajectory, ball_pos,
                      frame_width, frame_height, None,
                      stumps_zone, fps=fps,
                      reason='Bounce detect nahi hui — pitching judge nahi ho sakti')
    pitch_point = trajectory[bounce_idx]
    pitch_x = pitch_point[0]
    pitched_outside_leg = _outside_leg(pitch_x)

    if pitched_outside_leg:
        steps.append({'step': 2, 'check': 'Pitching',
                      'result': 'OUTSIDE LEG — NOT OUT', 'pass': False})
        return _final('NOT OUT', 95, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, fps=fps, reason='Leg stump ke bahar pitch — Law 36')
    # Pitching in line ya outside off — dono acceptable
    pitch_in_line = stumps_zone[0] <= pitch_x <= stumps_zone[1]
    pitch_overlap = (_overlap_fraction(pitch_x, ball_radius_px, stumps_zone)
                     if pitch_in_line else None)
    steps.append({'step': 2, 'check': 'Pitching',
                  'result': 'IN LINE' if pitch_in_line else 'OUTSIDE OFF',
                  'pass': True})

    # ===== STEP 3: BAT INVOLVED? =====
    if bat_involved:
        steps.append({'step': 3, 'check': 'Bat involved',
                      'result': 'BAT FIRST — NOT OUT', 'pass': False})
        return _final('NOT OUT', 90, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, fps=fps, reason='Pehle bat laga — LBW nahi')
    steps.append({'step': 3, 'check': 'Bat involved',
                  'result': 'No bat — pad first', 'pass': True})

    # ===== STEP 4: IMPACT (BE-H3: leg ke bahar impact kabhi nahi) =====
    impact_x = ball_pos[0]
    impact_in_line = stumps_zone[0] <= impact_x <= stumps_zone[1]

    if _outside_leg(impact_x):
        # No-shot exception sirf OFF side ke liye hai — leg stump ke
        # bahar impact, shot ho ya na ho, hamesha NOT OUT.
        steps.append({'step': 4, 'check': 'Impact',
                      'result': 'OUTSIDE LEG — NOT OUT', 'pass': False})
        return _final('NOT OUT', 95, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, fps=fps,
                      reason='Leg stump ke bahar impact — Law 36 (shot se farq nahi)')
    if playing_shot and not impact_in_line:
        steps.append({'step': 4, 'check': 'Impact',
                      'result': 'OUTSIDE LINE (shot khela) — NOT OUT',
                      'pass': False})
        return _final('NOT OUT', 90, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, fps=fps,
                      reason='Shot khelne par impact line me hona chahiye')
    # No-shot + outside-off pass: label sirf outside-off ke liye (BE-H3).
    impact_overlap = (_overlap_fraction(impact_x, ball_radius_px, stumps_zone)
                      if impact_in_line else None)
    steps.append({'step': 4, 'check': 'Impact',
                  'result': 'IN LINE' if impact_in_line else
                            'OUTSIDE OFF (no shot — OK)',
                  'pass': True})

    # ===== STEP 5: WICKETS HITTING (BE-H1: pre-impact segment) =====
    # Live trajectory ka aakhri point IMPACT point hai (pad deflection
    # included) — direction ke liye usse pehle ka segment lo.
    if len(trajectory) >= 3 and tuple(trajectory[-1]) == tuple(ball_pos):
        pre_impact = trajectory[:-1]
    else:
        pre_impact = trajectory
    if len(pre_impact) < 2:
        pre_impact = trajectory
    is_hitting, predicted_path, hitting_overlap = _predict_path(
        pre_impact, stumps_zone, frame_width, frame_height=frame_height,
        ground_y=pitch_point[1], stump_height_px=stump_height_px,
        ball_radius_px=ball_radius_px)
    # Impact line me nahi to projection bhi nahi
    is_hitting = is_hitting and (impact_in_line or not playing_shot)

    if not is_hitting:
        steps.append({'step': 5, 'check': 'Hitting wickets',
                      'result': 'MISSING — NOT OUT', 'pass': False})
        return _final('NOT OUT', 85, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, fps=fps, reason='Ball stumps par nahi lagti',
                      predicted_path=predicted_path)

    steps.append({'step': 5, 'check': 'Hitting wickets',
                  'result': 'HITTING', 'pass': True})

    # ===== STEP 6: UMPIRE'S CALL (BE-H2: real 50% overlap rule) =====
    # Sirf wahi fractions marginality me gino jo "in line" hone ka daava
    # karte hain: outside-off pitch / no-shot outside-off impact legal
    # passes hain, marginal nahi — unhe 0 fraction ki tarah ginna galat
    # hota (wo on-field NOT OUT ko bacha lete jabki ball saaf hitting hai).
    fractions = {}
    if pitch_overlap is not None:
        fractions['pitch'] = pitch_overlap
    if impact_overlap is not None:
        fractions['impact'] = impact_overlap
    fractions['hitting'] = hitting_overlap
    marginal = {k: v for k, v in fractions.items() if v < 0.5}
    # Note: hitting_overlap > 0 yahan guaranteed hai (step 5 pass), aur
    # pitch/impact overlap in-line hone par > 0 hota hai.
    min_frac = min(fractions.values()) if fractions else 1.0

    if marginal:
        # Umpire's Call — on-field decision rehta hai
        decision = on_field_call
        confidence = round(50.0 + 40.0 * min_frac, 2)
        steps.append({'step': 6, 'check': "Umpire's Call",
                      'result': f'MARGINAL ({", ".join(sorted(marginal))}) '
                                f'— on-field "{on_field_call}" stands',
                      'pass': True})
        return _final(decision, confidence, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, fps=fps,
                      reason=f"Marginal call — umpire's call ({on_field_call})",
                      predicted_path=predicted_path,
                      umpires_call=True,
                      overlap_fractions=fractions)
    else:
        decision = 'OUT'
        reason = 'Sab checks pass — OUT!'
        confidence = round(min(97.0, 85.0 + 12.0 * min_frac), 2)

    steps.append({'step': 6, 'check': "Umpire's Call",
                  'result': 'CLEAR — no umpire\'s call needed', 'pass': True})

    return _final(decision, confidence, steps, trajectory, ball_pos,
                  frame_width, frame_height, pitch_point,
                  stumps_zone, fps=fps, reason=reason,
                  predicted_path=predicted_path,
                  overlap_fractions=fractions)


def _final(decision, confidence, steps, trajectory, ball_pos,
           frame_width, frame_height, pitch_point, stumps_zone,
           reason='', predicted_path=None, umpires_call=False, fps=30,
           overlap_fractions=None):
    """Standard result format."""
    # Cricket intelligence
    try:
        from core_processing.ball_physics import analyze_delivery as _ad
        _delivery = _ad(trajectory, fps=fps, frame_width=frame_width)
    except Exception:
        _delivery = None

    # BE-H9 compat fields — actual step results se, na ki pass-flag ya
    # hardcoded value se: pitching 'IN LINE' tabhi jab step 2 ne wahi
    # kaha ho (outside-off pass pitch_in_line=False deta hai), impact
    # tabhi jab step 4 'IN LINE' ho, hitting tabhi jab step 5 'HITTING'.
    pitch_in_line = any(
        s['check'] == 'Pitching' and s['result'] == 'IN LINE'
        for s in steps)
    impact_in_line = any(
        s['check'] == 'Impact' and s['result'] == 'IN LINE'
        for s in steps)
    hitting_wickets = any(
        s['check'] == 'Hitting wickets' and s['result'] == 'HITTING'
        for s in steps)

    return {
        'final_decision': decision,
        'decision': decision,  # backward compat
        'confidence': confidence,
        'reason': reason,
        'umpires_call': umpires_call,
        'steps': steps,  # TV-style step-by-step!
        'trajectory_points': len(trajectory),
        'frame_width': frame_width,
        'frame_height': frame_height,
        'pitch_point': ([pitch_point[0], pitch_point[1]]
                        if pitch_point is not None else [None, None]),
        'impact_point': [ball_pos[0], ball_pos[1]],
        'stumps_zone': [stumps_zone[0], stumps_zone[1]],
        'trajectory': [[p[0], p[1]] for p in trajectory[-30:]],
        'predicted_path': predicted_path or [],
        'delivery_analysis': _delivery,
        # BE-H9: ye teen fields ab jhooth nahi bolte.
        'pitch_in_line': pitch_in_line,
        'impact_in_line': impact_in_line,
        'hitting_wickets': hitting_wickets,
        'overlap_fractions': overlap_fractions,
    }


# Backward compatibility — purana function ab ICC version ko call karta hai
def analyze_lbw_rules(tracking_data, frame_width, frame_height=None, fps=30,
                      **kwargs):
    """ICC version ka wrapper. kwargs (is_no_ball, playing_shot,
    bat_involved, on_field_call, stumps_zone, leg_side_x, handedness,
    stump_height_px, ball_radius_px) seedhe analyze_lbw_icc ko jaate
    hain — tasks.py isi se bat/no-ball/shot evidence pass karta hai
    (BE-H7), warna defaults (RHB, shot khela, no bat, no no-ball)."""
    result = analyze_lbw_icc(tracking_data, frame_width, frame_height,
                             fps=fps, **kwargs)
    if result is None:
        return None
    # CV-C4: surface the tracker's fallback flag in the result, so the
    # API/DB record (via tasks.py -> Review.analysis_data) whether this
    # decision ran on the real cricket model or a fallback model.
    metrics = (tracking_data or {}).get('metrics') or {}
    result['using_fallback'] = bool(metrics.get('using_fallback', False))
    return result

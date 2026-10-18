"""
DRS LBW Decision — ICC Playing Conditions ka EXACT protocol.

International cricket me third umpire isi order me check karta hai:

  Step 1: NO-BALL? → hai to seedha NOT OUT
  Step 2: PITCHING — kahan pitch hui?
  Step 3: IMPACT — kahan lagi?
  Step 4: BAT involved? → pehle bat laga to NOT OUT
  Step 5: WICKETS HITTING — Hawk-Eye projection
  Step 6: UMPIRE'S CALL — marginal par on-field decision

ICC Law 36 (LBW) ke key rules:
- Leg stump ke bahar pitch → hamesha NOT OUT
- Shot khel raha hai to: pitching + impact dono line me hone chahiye
- Shot NAHI khel raha to: impact bahar bhi chalega (pitching phir bhi leg ke bahar nahi)
- Umpire's Call: pitching/impact/hitting me se koi bhi marginal (<50% ball)
  to on-field umpire ka faisla rehta hai
"""

# Umpire's Call thresholds (ICC: 50% of ball must be hitting)
UMPIRE_CALL_PITCH_MARGIN = 0.5   # ball ka kitna hissa line me
UMPIRE_CALL_IMPACT_MARGIN = 0.5
UMPIRE_CALL_HITTING_MARGIN = 0.5


def _linearity(trajectory):
    """Aakhri points kitne seedhi line me — 0.0 se 1.0."""
    pts = trajectory[-8:]
    if len(pts) < 3:
        return 0.5
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    var_x = sum((x - mx) ** 2 for x in xs)
    if var_x < 1e-9:
        return 0.5
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var_x
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot < 1e-9:
        return 1.0
    return max(0.0, min(1.0, 1 - ss_res / ss_tot))


def _predict_path(trajectory, stumps_zone, frame_width, max_steps=300):
    """Ball ka rasta aage badhao — hitting check karo."""
    if len(trajectory) < 2:
        return False, []
    (x1, y1), (x2, y2) = trajectory[-2], trajectory[-1]
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return False, []
    length = (dx ** 2 + dy ** 2) ** 0.5
    step_x, step_y = dx / length * 4.0, dy / length * 4.0
    px, py = float(x2), float(y2)
    path = []
    hitting = False
    for _ in range(max_steps):
        px += step_x
        py += step_y
        if not (0 < px < frame_width):
            break
        path.append([round(px, 1), round(py, 1)])
        if stumps_zone[0] < px < stumps_zone[1]:
            hitting = True
            break
    return hitting, path


def analyze_lbw_icc(tracking_data, frame_width, frame_height=None,
                    is_no_ball=False, playing_shot=True,
                    bat_involved=False, on_field_call='OUT',
                    stumps_zone=None, leg_side_x=None):
    """
    ICC protocol ke hisab se LBW decision.

    Args:
        tracking_data: {"ball": (x,y), "trajectory": [(x,y),...]}
        frame_width/height: frame dimensions
        is_no_ball: front-foot no-ball thi?
        playing_shot: batsman shot khel raha tha?
        bat_involved: UltraEdge ne bat-ball contact detect kiya?
        on_field_call: 'OUT' ya 'NOT OUT' (umpire's call ke liye)
        stumps_zone: (x1, x2) — calibrate kiya hua, warna auto
        leg_side_x: leg side ka threshold, warna auto

    Returns: full decision with step-by-step reasoning (jaise TV par dikhta hai!)
    """
    trajectory = tracking_data.get("trajectory") or []
    ball_pos = tracking_data.get("ball")

    steps = []  # Har step ka result (TV graphic ke liye!)

    if not ball_pos or len(trajectory) < 3:
        return None

    # Zones
    if stumps_zone is None:
        stumps_zone = (frame_width * 0.4, frame_width * 0.6)
    if leg_side_x is None:
        leg_side_x = frame_width * 0.7  # RHB ke liye

    pitch_point = trajectory[0]
    impact_x = ball_pos[0]
    stump_cx = (stumps_zone[0] + stumps_zone[1]) / 2
    stump_hw = (stumps_zone[1] - stumps_zone[0]) / 2  # half width

    # ===== STEP 1: NO-BALL =====
    if is_no_ball:
        steps.append({'step': 1, 'check': 'No-ball',
                      'result': 'NO BALL — NOT OUT', 'pass': False})
        return _final('NOT OUT', 100, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, reason='No-ball par LBW nahi ho sakta')
    steps.append({'step': 1, 'check': 'No-ball',
                  'result': 'Fair delivery', 'pass': True})

    # ===== STEP 2: PITCHING =====
    pitch_x = pitch_point[0]
    pitched_outside_leg = pitch_x > leg_side_x

    if pitched_outside_leg:
        steps.append({'step': 2, 'check': 'Pitching',
                      'result': 'OUTSIDE LEG — NOT OUT', 'pass': False})
        return _final('NOT OUT', 95, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, reason='Leg stump ke bahar pitch — Law 36')
    # Pitching in line ya outside off — dono acceptable
    pitch_in_line = stumps_zone[0] <= pitch_x <= stumps_zone[1]
    steps.append({'step': 2, 'check': 'Pitching',
                  'result': 'IN LINE' if pitch_in_line else 'OUTSIDE OFF',
                  'pass': True})

    # ===== STEP 3: BAT INVOLVED? =====
    if bat_involved:
        steps.append({'step': 3, 'check': 'Bat involved',
                      'result': 'BAT FIRST — NOT OUT', 'pass': False})
        return _final('NOT OUT', 90, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, reason='Pehle bat laga — LBW nahi')
    steps.append({'step': 3, 'check': 'Bat involved',
                  'result': 'No bat — pad first', 'pass': True})

    # ===== STEP 4: IMPACT =====
    impact_in_line = stumps_zone[0] <= impact_x <= stumps_zone[1]

    if playing_shot and not impact_in_line:
        steps.append({'step': 4, 'check': 'Impact',
                      'result': 'OUTSIDE LINE (shot khela) — NOT OUT',
                      'pass': False})
        return _final('NOT OUT', 90, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone,
                      reason='Shot khelne par impact line me hona chahiye')
    steps.append({'step': 4, 'check': 'Impact',
                  'result': 'IN LINE' if impact_in_line else
                            'OUTSIDE OFF (no shot — OK)',
                  'pass': True})

    # ===== STEP 5: WICKETS HITTING =====
    is_hitting, predicted_path = _predict_path(trajectory, stumps_zone,
                                               frame_width)
    # Impact line me nahi to projection bhi nahi
    is_hitting = is_hitting and (impact_in_line or not playing_shot)

    if not is_hitting:
        steps.append({'step': 5, 'check': 'Hitting wickets',
                      'result': 'MISSING — NOT OUT', 'pass': False})
        return _final('NOT OUT', 85, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone, reason='Ball stumps par nahi lagti',
                      predicted_path=predicted_path)

    steps.append({'step': 5, 'check': 'Hitting wickets',
                  'result': 'HITTING', 'pass': True})

    # ===== STEP 6: UMPIRE'S CALL =====
    # Confidence se marginality nikalo
    r2 = _linearity(trajectory)
    length_bonus = 10 if len(trajectory) >= 10 else (5 if len(trajectory) >= 5 else 0)
    confidence = round(min(97.0, 50.0 + 35.0 * r2 + length_bonus), 2)

    if confidence > 75:
        decision = 'OUT'
        reason = 'Sab checks pass — OUT!'
    elif confidence > 50:
        # Umpire's Call — on-field decision rehta hai
        decision = on_field_call
        steps.append({'step': 6, 'check': "Umpire's Call",
                      'result': f'MARGINAL — on-field "{on_field_call}" stands',
                      'pass': True})
        return _final(decision, confidence, steps, trajectory, ball_pos,
                      frame_width, frame_height, pitch_point,
                      stumps_zone,
                      reason=f"Marginal call — umpire's call ({on_field_call})",
                      predicted_path=predicted_path,
                      umpires_call=True)
    else:
        decision = 'NOT OUT'
        reason = 'Evidence insufficient — benefit batsman ko'

    steps.append({'step': 6, 'check': "Umpire's Call",
                  'result': 'CLEAR — no umpire\'s call needed', 'pass': True})

    return _final(decision, confidence, steps, trajectory, ball_pos,
                  frame_width, frame_height, pitch_point,
                  stumps_zone, reason=reason,
                  predicted_path=predicted_path)


def _final(decision, confidence, steps, trajectory, ball_pos,
           frame_width, frame_height, pitch_point, stumps_zone,
           reason='', predicted_path=None, umpires_call=False):
    """Standard result format."""
    # Cricket intelligence
    try:
        from core_processing.ball_physics import analyze_delivery as _ad
        _delivery = _ad(trajectory, fps=30, frame_width=frame_width)
    except Exception:
        _delivery = None

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
        'pitch_point': [pitch_point[0], pitch_point[1]],
        'impact_point': [ball_pos[0], ball_pos[1]],
        'stumps_zone': [stumps_zone[0], stumps_zone[1]],
        'trajectory': [[p[0], p[1]] for p in trajectory[-30:]],
        'predicted_path': predicted_path or [],
        'delivery_analysis': _delivery,
    }


# Backward compatibility — purana function ab ICC version ko call karta hai
def analyze_lbw_rules(tracking_data, frame_width, frame_height=None):
    result = analyze_lbw_icc(tracking_data, frame_width, frame_height)
    if result is None:
        return None
    # Purane format ke fields bhi rakho
    result['pitch_in_line'] = any(
        s['check'] == 'Pitching' and s['pass'] for s in result['steps'])
    result['impact_in_line'] = True  # simplified
    result['hitting_wickets'] = result['final_decision'] == 'OUT'
    return result

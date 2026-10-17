"""
Pitch Map — broadcast-standard bowler analysis.

Har ball kahan pitch hui, uska map. Ye TV par dikhta hai!
- Good length, short, full, yorker zones
- Line: off stump, middle, leg stump
- Color: dots (green), runs (blue), wickets (red)

Usage:
    from core_processing.pitch_map import PitchMap
    pm = PitchMap()
    pm.add_delivery(pitch_x=2.5, pitch_y=0.1, outcome='dot', speed=135)
    pm.add_delivery(pitch_x=1.2, pitch_y=-0.3, outcome='wicket', speed=142)
    svg = pm.to_svg()  # frontend me dikhao
    stats = pm.get_stats()  # bowler analysis
"""

# Pitch zones (meters from batsman stumps, x = distance)
# x: 0 = stumps, positive = bowler ki taraf
ZONE_YORKER = (0, 1.0)
ZONE_FULL = (1.0, 3.0)
ZONE_GOOD = (3.0, 6.0)
ZONE_SHORT = (6.0, 10.0)

OUTCOME_COLORS = {
    'dot': '#22c55e',      # green
    'run': '#3b82f6',      # blue
    'boundary': '#a855f7',  # purple
    'wicket': '#ef4444',    # red
    'wide': '#f59e0b',      # orange
    'noball': '#f59e0b',
}


def classify_length(pitch_x):
    """Pitch distance se length classify karo."""
    if pitch_x < ZONE_YORKER[1]:
        return 'Yorker'
    elif pitch_x < ZONE_FULL[1]:
        return 'Full'
    elif pitch_x < ZONE_GOOD[1]:
        return 'Good length'
    else:
        return 'Short'


def classify_line(pitch_y):
    """Lateral position se line classify karo."""
    if pitch_y > 0.3:
        return 'Wide outside off'
    elif pitch_y > 0.1:
        return 'Outside off'
    elif pitch_y > -0.1:
        return 'Off stump'
    elif pitch_y > -0.3:
        return 'Middle stump'
    else:
        return 'Leg stump'


class PitchMap:
    def __init__(self, bowler_name="Bowler"):
        self.bowler_name = bowler_name
        self.deliveries = []  # [(pitch_x, pitch_y, outcome, speed, ...), ...]

    def add_delivery(self, pitch_x, pitch_y, outcome='dot',
                     speed_kmh=None, swing=None, spin=None):
        """
        Ek ball add karo.
        pitch_x: stumps se distance (meters, bowler ki taraf positive)
        pitch_y: lateral (meters, + = off side for RHB)
        outcome: 'dot' | 'run' | 'boundary' | 'wicket' | 'wide' | 'noball'
        """
        self.deliveries.append({
            'pitch_x': pitch_x,
            'pitch_y': pitch_y,
            'outcome': outcome,
            'speed_kmh': speed_kmh,
            'length': classify_length(pitch_x),
            'line': classify_line(pitch_y),
            'swing': swing,
            'spin': spin,
        })

    def get_stats(self):
        """Bowler ka summary."""
        if not self.deliveries:
            return {'total': 0}

        n = len(self.deliveries)
        speeds = [d['speed_kmh'] for d in self.deliveries if d['speed_kmh']]
        lengths = {}
        lines = {}
        outcomes = {}
        for d in self.deliveries:
            lengths[d['length']] = lengths.get(d['length'], 0) + 1
            lines[d['line']] = lines.get(d['line'], 0) + 1
            outcomes[d['outcome']] = outcomes.get(d['outcome'], 0) + 1

        return {
            'total': n,
            'bowler': self.bowler_name,
            'avg_speed': round(sum(speeds)/len(speeds), 1) if speeds else None,
            'max_speed': round(max(speeds), 1) if speeds else None,
            'lengths': lengths,
            'lines': lines,
            'outcomes': outcomes,
            'dot_ball_pct': round(outcomes.get('dot', 0)/n*100, 1),
            'wickets': outcomes.get('wicket', 0),
        }

    def to_svg(self, width=400, height=500):
        """
        Broadcast-style pitch map SVG.
        Pitch vertical: upar = bowler, neeche = batsman.
        """
        # Coordinate mapping:
        # pitch_x: 0-10m → y: height-50 (stumps) to 50 (bowler)
        # pitch_y: -1 to +1m → x: 50 to width-50
        def px(pitch_y):
            return 50 + (pitch_y + 1) / 2 * (width - 100)

        def py(pitch_x):
            # 0m → neeche, 10m → upar
            return (height - 50) - (pitch_x / 10) * (height - 100)

        svg = [
            f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg">',
            # Background
            f'<rect width="{width}" height="{height}" fill="#1a472a" rx="8"/>',
            # Pitch strip
            f'<rect x="{px(-0.5)}" y="30" width="{px(0.5)-px(-0.5)}" '
            f'height="{height-60}" fill="#c2a878" rx="4" opacity="0.9"/>',
            # Zone lines
            f'<line x1="30" y1="{py(1)}" x2="{width-30}" y2="{py(1)}" '
            f'stroke="#fff" stroke-dasharray="4" opacity="0.4"/>',
            f'<text x="{width-35}" y="{py(1)-5}" fill="#fff" font-size="10" '
            f'text-anchor="end" opacity="0.7">Yorker</text>',
            f'<line x1="30" y1="{py(3)}" x2="{width-30}" y2="{py(3)}" '
            f'stroke="#fff" stroke-dasharray="4" opacity="0.4"/>',
            f'<text x="{width-35}" y="{py(3)-5}" fill="#fff" font-size="10" '
            f'text-anchor="end" opacity="0.7">Full</text>',
            f'<line x1="30" y1="{py(6)}" x2="{width-30}" y2="{py(6)}" '
            f'stroke="#fff" stroke-width="2" opacity="0.6"/>',
            f'<text x="{width-35}" y="{py(6)-5}" fill="#fff" font-size="10" '
            f'text-anchor="end" opacity="0.7">Good</text>',
            # Stumps
            f'<rect x="{px(-0.11)-3}" y="{height-55}" width="6" height="20" fill="#fff"/>',
            f'<rect x="{px(0)-3}" y="{height-55}" width="6" height="20" fill="#fff"/>',
            f'<rect x="{px(0.11)-3}" y="{height-55}" width="6" height="20" fill="#fff"/>',
            # Title
            f'<text x="{width/2}" y="22" fill="#fff" font-size="14" '
            f'text-anchor="middle" font-weight="bold">{self.bowler_name} — Pitch Map</text>',
        ]

        # Deliveries
        for i, d in enumerate(self.deliveries):
            cx, cy = px(d['pitch_y']), py(d['pitch_x'])
            color = OUTCOME_COLORS.get(d['outcome'], '#fff')
            svg.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="{color}" '
                f'stroke="#fff" stroke-width="1.5" opacity="0.9">'
                f'<title>Ball {i+1}: {d["length"]}, {d["line"]}, '
                f'{d["speed_kmh"] or "?"} km/h, {d["outcome"]}</title>'
                f'</circle>'
            )
            svg.append(
                f'<text x="{cx:.1f}" y="{cy+4:.1f}" fill="#fff" font-size="9" '
                f'text-anchor="middle" font-weight="bold">{i+1}</text>'
            )

        # Legend
        legend_y = height - 15
        lx = 20
        for outcome, color in OUTCOME_COLORS.items():
            if outcome in ['wide', 'noball']:
                continue
            svg.append(f'<circle cx="{lx}" cy="{legend_y}" r="6" fill="{color}"/>')
            svg.append(f'<text x="{lx+10}" y="{legend_y+4}" fill="#fff" '
                       f'font-size="10">{outcome}</text>')
            lx += 70

        svg.append('</svg>')
        return '\n'.join(svg)

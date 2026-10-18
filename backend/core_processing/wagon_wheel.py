"""
Wagon Wheel — batting analytics (StreetDRS spec S1, MANDATORY).

Batsman ne kahan-kahan shot mare — ground ke around plot.
- Har shot: direction (angle), runs, ball number
- Color: 1s (blue), 2s (green), 3s (yellow), 4s (orange), 6s (red)
- Filter: batter, bowler, over

Usage:
    from core_processing.wagon_wheel import WagonWheel
    ww = WagonWheel(batter_name="Kohli")
    ww.add_shot(angle_deg=45, runs=4, ball=3, over=1)  # cover drive!
    ww.add_shot(angle_deg=180, runs=6, ball=5, over=2)  # long on!
    svg = ww.to_svg()
"""

import math

# Shot zones by angle (0° = straight down the ground, batter's perspective)
# Angle: 0 = straight, 90 = cover/point, 180 = behind (fine leg), 270 = midwicket
SHOT_ZONES = {
    (315, 45): 'Straight (V)',
    (45, 90): 'Cover',
    (90, 135): 'Point',
    (135, 180): 'Third man',
    (180, 225): 'Fine leg',
    (225, 270): 'Square leg',
    (270, 315): 'Midwicket / Long on',
}

RUN_COLORS = {
    0: '#9ca3af',  # dot - grey
    1: '#3b82f6',  # blue
    2: '#22c55e',  # green
    3: '#eab308',  # yellow
    4: '#f97316',  # orange
    6: '#ef4444',  # red
}


def classify_shot_zone(angle_deg):
    """Angle se shot zone ka naam."""
    angle_deg = angle_deg % 360
    for (lo, hi), name in SHOT_ZONES.items():
        if lo <= hi:
            if lo <= angle_deg < hi:
                return name
        else:  # wraps around 0
            if angle_deg >= lo or angle_deg < hi:
                return name
    return 'Unknown'


class WagonWheel:
    def __init__(self, batter_name="Batsman"):
        self.batter_name = batter_name
        self.shots = []  # [{angle, runs, ball, over, ...}]

    def add_shot(self, angle_deg, runs=0, ball=None, over=None,
                 bowler=None, confirmed=True):
        """
        Ek shot add karo.
        angle_deg: 0=straight, 90=cover, 180=fine leg, 270=midwicket
        confirmed: True = human verified, False = AI estimated
        """
        self.shots.append({
            'angle': angle_deg % 360,
            'runs': runs,
            'ball': ball,
            'over': over,
            'bowler': bowler,
            'zone': classify_shot_zone(angle_deg),
            'confirmed': confirmed,
        })

    def get_stats(self):
        """Batting analysis."""
        if not self.shots:
            return {'total_shots': 0}

        total_runs = sum(s['runs'] for s in self.shots)
        zones = {}
        for s in self.shots:
            z = s['zone']
            if z not in zones:
                zones[z] = {'shots': 0, 'runs': 0}
            zones[z]['shots'] += 1
            zones[z]['runs'] += s['runs']

        # Favorite zone
        fav = max(zones.items(), key=lambda x: x[1]['runs']) if zones else (None, {})

        return {
            'batter': self.batter_name,
            'total_shots': len(self.shots),
            'total_runs': total_runs,
            'boundaries': sum(1 for s in self.shots if s['runs'] >= 4),
            'fours': sum(1 for s in self.shots if s['runs'] == 4),
            'sixes': sum(1 for s in self.shots if s['runs'] == 6),
            'zones': zones,
            'favorite_zone': fav[0],
            'favorite_zone_runs': fav[1].get('runs', 0),
        }

    def to_svg(self, size=400):
        """Broadcast-style wagon wheel SVG."""
        cx, cy = size // 2, size // 2
        R = size // 2 - 30  # boundary rope radius

        svg = [
            f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
            f'xmlns="http://www.w3.org/2000/svg">',
            # Ground
            f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#2d6a4f" '
            f'stroke="#fff" stroke-width="3"/>',
            f'<circle cx="{cx}" cy="{cy}" r="{R-8}" fill="none" '
            f'stroke="#fff" stroke-width="1" stroke-dasharray="6" opacity="0.5"/>',
            # Pitch (center)
            f'<rect x="{cx-12}" y="{cy-35}" width="24" height="70" '
            f'fill="#c2a878" rx="3"/>',
            # Title
            f'<text x="{cx}" y="20" fill="#fff" font-size="13" '
            f'text-anchor="middle" font-weight="bold">'
            f'{self.batter_name} — Wagon Wheel</text>',
        ]

        # Zone labels
        for (lo, hi), name in SHOT_ZONES.items():
            mid = (lo + hi) / 2 if lo < hi else ((lo + hi + 360) / 2) % 360
            rad = math.radians(mid - 90)  # 0° = up
            lx = cx + (R - 18) * math.cos(rad)
            ly = cy + (R - 18) * math.sin(rad)
            short = name.split(' ')[0]
            svg.append(
                f'<text x="{lx:.0f}" y="{ly:.0f}" fill="#fff" font-size="8" '
                f'text-anchor="middle" opacity="0.6">{short}</text>'
            )

        # Shots (lines from center outward)
        for i, s in enumerate(self.shots):
            rad = math.radians(s['angle'] - 90)
            # Distance by runs: dots short, 6s to boundary
            dist_map = {0: 0.3, 1: 0.5, 2: 0.6, 3: 0.7, 4: 0.85, 6: 0.98}
            dist = R * dist_map.get(s['runs'], 0.5)
            x2 = cx + dist * math.cos(rad)
            y2 = cy + dist * math.sin(rad)
            color = RUN_COLORS.get(s['runs'], '#fff')
            width = 3 if s['runs'] >= 4 else 2
            dash = '' if s['confirmed'] else ' stroke-dasharray="4"'

            svg.append(
                f'<line x1="{cx}" y1="{cy}" x2="{x2:.0f}" y2="{y2:.0f}" '
                f'stroke="{color}" stroke-width="{width}"{dash} opacity="0.85">'
                f'<title>{s["zone"]}: {s["runs"]} run(s)</title></line>'
            )
            # Dot at end
            svg.append(
                f'<circle cx="{x2:.0f}" cy="{y2:.0f}" r="4" fill="{color}" '
                f'stroke="#fff" stroke-width="1"/>'
            )

        # Legend
        ly = size - 12
        lx = 15
        for runs, color in [(1, '#3b82f6'), (2, '#22c55e'), (4, '#f97316'), (6, '#ef4444')]:
            svg.append(f'<circle cx="{lx}" cy="{ly}" r="5" fill="{color}"/>')
            svg.append(f'<text x="{lx+8}" y="{ly+4}" fill="#fff" font-size="9">{runs}</text>')
            lx += 32
        svg.append(
            f'<text x="{lx+5}" y="{ly+4}" fill="#fff" font-size="9" opacity="0.6">'
            f'dashed = AI estimate</text>'
        )

        svg.append('</svg>')
        return '\n'.join(svg)

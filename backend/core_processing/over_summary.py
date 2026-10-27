"""
Over Summary — 6 balls ka complete analysis dashboard data.

Har over ke liye:
- Har ball: speed, length, line, outcome, LBW decision
- Bowler stats: avg speed, dot %, wickets
- Pitch map SVG
- Wagon wheel data (agar shot tracking ho)

Usage:
    from core_processing.over_summary import OverSummary
    over = OverSummary(over_number=1, bowler="Bumrah", batsman="Kohli")
    over.add_ball(ball_data)  # ball_data: dict from analysis pipeline
    summary = over.get_summary()
    html = over.to_html_report()
"""

from core_processing.pitch_map import PitchMap


class OverSummary:
    def __init__(self, over_number=1, bowler="Bowler", batsman="Batsman"):
        self.over_number = over_number
        self.bowler = bowler
        self.batsman = batsman
        self.balls = []
        self.pitch_map = PitchMap(bowler_name=bowler)

    def add_ball(self, ball_data):
        """
        ball_data: {
            'pitch_3d': (x, y, z) | None,
            'decision': 'OUT' | 'NOT OUT' | ...,
            'confidence': float,
            'delivery_analysis': {'speed_kmh': ..., 'delivery_type': ..., ...},
            'outcome': 'dot' | 'run' | 'boundary' | 'wicket' | 'wide',
            'runs': int,
        }
        """
        ball_num = len(self.balls) + 1
        self.balls.append({'ball': ball_num, **ball_data})

        # Pitch map me add karo
        pitch = ball_data.get('pitch_3d')
        if pitch:
            # pitch_x: stumps se distance (10.06 - x)
            pitch_x = 10.06 - pitch[0]
            pitch_y = pitch[1]
            da = ball_data.get('delivery_analysis', {})
            self.pitch_map.add_delivery(
                pitch_x=pitch_x,
                pitch_y=pitch_y,
                outcome=ball_data.get('outcome', 'dot'),
                speed_kmh=da.get('speed_kmh'),
            )

    def get_summary(self):
        """Over ka summary dict."""
        total_runs = sum(b.get('runs', 0) for b in self.balls)
        wickets = sum(1 for b in self.balls if b.get('outcome') == 'wicket')
        dots = sum(1 for b in self.balls if b.get('outcome') == 'dot')
        speeds = [b.get('delivery_analysis', {}).get('speed_kmh')
                  for b in self.balls
                  if b.get('delivery_analysis', {}).get('speed_kmh')]

        # LBW shouts (BE-L2): drs_logic kabhi "UMPIRE'S CALL" decision
        # emit nahi karta — wo on-field call ('OUT'/'NOT OUT') deta hai
        # umpires_call=True ke saath — isliye marginal appeals bhi gino.
        lbw_appeals = [b for b in self.balls
                       if b.get('decision') in ('OUT', "UMPIRE'S CALL")
                       or b.get('umpires_call') is True]

        return {
            'over': self.over_number,
            'bowler': self.bowler,
            'batsman': self.batsman,
            'balls': len(self.balls),
            'runs': total_runs,
            'wickets': wickets,
            'dots': dots,
            'avg_speed': round(sum(speeds)/len(speeds), 1) if speeds else None,
            'max_speed': round(max(speeds), 1) if speeds else None,
            'lbw_appeals': len(lbw_appeals),
            'pitch_map_stats': self.pitch_map.get_stats(),
            'balls_detail': self.balls,
        }

    def to_html_report(self):
        """Simple HTML report — PDF banane ke liye bhi use hota hai."""
        # BE-M6: bowler/batsman names raw interpolate nahi hote — HTML
        # escape karo (XSS vector tha).
        import html as _html
        bowler = _html.escape(str(self.bowler))
        batsman = _html.escape(str(self.batsman))
        s = self.get_summary()
        s = dict(s)
        s['bowler'] = bowler
        s['batsman'] = batsman
        html = f"""
        <html><head><style>
        body {{ font-family: Arial; margin: 20px; }}
        h1 {{ color: #1a472a; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #1a472a; color: white; }}
        .stat {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .stat b {{ font-size: 24px; color: #1a472a; }}
        </style></head><body>
        <h1>Over {s['over']} Summary</h1>
        <p><b>Bowler:</b> {s['bowler']} | <b>Batsman:</b> {s['batsman']}</p>
        <div>
          <span class="stat"><b>{s['runs']}</b><br>Runs</span>
          <span class="stat"><b>{s['wickets']}</b><br>Wickets</span>
          <span class="stat"><b>{s['dots']}</b><br>Dots</span>
          <span class="stat"><b>{s['avg_speed'] or '-'}</b><br>Avg km/h</span>
          <span class="stat"><b>{s['max_speed'] or '-'}</b><br>Max km/h</span>
        </div>
        <h2>Ball by Ball</h2>
        <table>
        <tr><th>Ball</th><th>Speed</th><th>Length</th><th>Line</th>
            <th>Outcome</th><th>LBW</th></tr>
        """
        # BE-H8: header me 6 columns hain (Ball, Speed, Length, Line,
        # Outcome, LBW) — har row me bhi 6 <td> hone chahiye. Pehle row
        # me sirf 5 the (delivery_type "Length" ke neeche tha, aur LBW
        # column khaali reh jaata tha).
        for b in s['balls_detail']:
            da = b.get('delivery_analysis', {})
            html += (f"<tr><td>{b['ball']}</td>"
                     f"<td>{da.get('speed_kmh', '-') or '-'}</td>"
                     f"<td>{da.get('delivery_type', '-')}</td>"
                     f"<td>{b.get('line', '-')}</td>"
                     f"<td>{b.get('outcome', '-')}</td>"
                     f"<td>{b.get('decision', '-')}</td></tr>")
        html += "</table>"
        html += f"<h2>Pitch Map</h2>{self.pitch_map.to_svg()}"
        html += "</body></html>"
        return html


def export_pdf(html_content, output_path):
    """
    HTML ko PDF me convert karo.
    WeasyPrint ya pdfkit me se jo available ho use karo.
    """
    # Try weasyprint
    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        return True
    except ImportError:
        pass

    # Try pdfkit (needs wkhtmltopdf)
    try:
        import pdfkit
        pdfkit.from_string(html_content, output_path)
        return True
    except ImportError:
        pass

    # Fallback: HTML hi save karo
    html_path = output_path.replace('.pdf', '.html')
    with open(html_path, 'w') as f:
        f.write(html_content)
    print(f"PDF libs nahi mile, HTML save kiya: {html_path}")
    print("Install karo: pip install weasyprint  (ya)  apt install wkhtmltopdf && pip install pdfkit")
    return False

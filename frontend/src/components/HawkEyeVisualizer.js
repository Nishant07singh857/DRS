import React from 'react';

// Broadcast-style Hawk-Eye visualization (SVG).
// analysis_data se banta hai: pitch_point, impact_point, trajectory,
// predicted_path, stumps_zone, frame_width/height.
const W = 1000;
const H = 540;

const COLORS = {
  OUT: '#ef4444',
  'NOT OUT': '#22c55e',
  "UMPIRE'S CALL": '#f59e0b',
};

function HawkEyeVisualizer({ analysis }) {
  if (!analysis || !analysis.pitch_point || !analysis.impact_point) {
    return (
      <div className="bg-gray-800 rounded-lg aspect-[16/9] flex items-center justify-center text-gray-500">
        No tracking data available for visualization.
      </div>
    );
  }

  const fw = analysis.frame_width || 1000;
  const fh = analysis.frame_height || fw * 0.5625;
  const mx = (x) => 70 + (x / fw) * 860;
  const my = (y) => 50 + (y / fh) * 380;

  const traj = (analysis.trajectory || []).map(([x, y]) => [mx(x), my(y)]);
  const pred = (analysis.predicted_path || []).map(([x, y]) => [mx(x), my(y)]);
  const pitch = [mx(analysis.pitch_point[0]), my(analysis.pitch_point[1])];
  const impact = [mx(analysis.impact_point[0]), my(analysis.impact_point[1])];
  const zone = analysis.stumps_zone || [fw * 0.4, fw * 0.6];
  const stumpX = mx((zone[0] + zone[1]) / 2);

  const line = (pts) => pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const pathD = (pts) =>
    pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const fullRoute = [...traj, ...pred];

  // Ground line data ke neeche taaki graphic anchored lage
  const maxY = Math.max(...fullRoute.map(([, y]) => y), 300);
  const groundY = Math.min(500, Math.max(400, maxY + 70));

  const decision = analysis.final_decision || 'N/A';
  const dColor = COLORS[decision] || '#9ca3af';
  const pitchColor = analysis.pitch_in_line ? '#22c55e' : '#fbbf24';
  const impactColor = analysis.impact_in_line ? '#22c55e' : '#ef4444';

  return (
    <div className="rounded-lg overflow-hidden shadow-2xl border border-gray-700">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full block" role="img" aria-label="Hawk-Eye ball tracking visualization">
        <defs>
          <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0b1f3a" />
            <stop offset="100%" stopColor="#123a2a" />
          </linearGradient>
          <linearGradient id="grass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#166534" />
            <stop offset="100%" stopColor="#14532d" />
          </linearGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background */}
        <rect width={W} height={H} fill="url(#sky)" />
        <rect y={groundY} width={W} height={H - groundY} fill="url(#grass)" opacity="0.85" />
        <line x1="0" y1={groundY} x2={W} y2={groundY} stroke="#ffffff" strokeOpacity="0.25" strokeWidth="2" />

        {/* Faint grid */}
        {[200, 400, 600, 800].map((x) => (
          <line key={x} x1={x} y1="0" x2={x} y2={H} stroke="#ffffff" strokeOpacity="0.05" />
        ))}
        {[150, 300, 450].map((y) => (
          <line key={y} x1="0" y1={y} x2={W} y2={y} stroke="#ffffff" strokeOpacity="0.05" />
        ))}

        {/* In-line corridor */}
        <rect
          x={mx(zone[0])} y="0" width={mx(zone[1]) - mx(zone[0])} height={H}
          fill="#ffffff" opacity="0.06"
        />
        <line x1={mx(zone[0])} y1="0" x2={mx(zone[0])} y2={H} stroke="#ffffff" strokeOpacity="0.2" strokeDasharray="6 6" />
        <line x1={mx(zone[1])} y1="0" x2={mx(zone[1])} y2={H} stroke="#ffffff" strokeOpacity="0.2" strokeDasharray="6 6" />
        <text x={(mx(zone[0]) + mx(zone[1])) / 2} y="24" textAnchor="middle" fill="#ffffff" opacity="0.5" fontSize="14" letterSpacing="3">
          STUMP LINE
        </text>

        {/* Stumps */}
        <g stroke="#fde047" strokeWidth="6" strokeLinecap="round">
          <line x1={stumpX - 10} y1={groundY} x2={stumpX - 10} y2={groundY - 78} />
          <line x1={stumpX} y1={groundY} x2={stumpX} y2={groundY - 78} />
          <line x1={stumpX + 10} y1={groundY} x2={stumpX + 10} y2={groundY - 78} />
        </g>
        <line x1={stumpX - 10} y1={groundY - 82} x2={stumpX + 10} y2={groundY - 82} stroke="#fde047" strokeWidth="4" strokeLinecap="round" />
        <text x={stumpX} y={groundY + 26} textAnchor="middle" fill="#fde047" fontSize="15" letterSpacing="2">STUMPS</text>

        {/* Tracked trajectory */}
        {traj.length > 1 && (
          <polyline points={line(traj)} fill="none" stroke="#ffffff" strokeOpacity="0.85" strokeWidth="3.5" filter="url(#glow)" strokeLinecap="round" />
        )}

        {/* Predicted path */}
        {pred.length > 1 && (
          <polyline points={line([impact, ...pred])} fill="none" stroke={dColor} strokeOpacity="0.9" strokeWidth="3" strokeDasharray="10 7" filter="url(#glow)" strokeLinecap="round" />
        )}
        {analysis.hitting_wickets && pred.length > 0 && (
          <circle cx={pred[pred.length - 1][0]} cy={pred[pred.length - 1][1]} r="9" fill={dColor} filter="url(#glow)">
            <animate attributeName="r" values="7;11;7" dur="1.2s" repeatCount="indefinite" />
          </circle>
        )}

        {/* Pitch marker */}
        <circle cx={pitch[0]} cy={pitch[1]} r="10" fill={pitchColor} stroke="#fff" strokeWidth="2" filter="url(#glow)" />
        <text x={pitch[0]} y={pitch[1] - 20} textAnchor="middle" fill="#fff" fontSize="14" fontWeight="bold" letterSpacing="1">PITCH</text>

        {/* Impact marker */}
        <circle cx={impact[0]} cy={impact[1]} r="13" fill={impactColor} opacity="0.35">
          <animate attributeName="r" values="11;19;11" dur="1.8s" repeatCount="indefinite" />
        </circle>
        <circle cx={impact[0]} cy={impact[1]} r="11" fill={impactColor} stroke="#fff" strokeWidth="2.5" filter="url(#glow)" />
        <text x={impact[0]} y={impact[1] - 26} textAnchor="middle" fill="#fff" fontSize="14" fontWeight="bold" letterSpacing="1">IMPACT</text>

        {/* Animated ball along full route */}
        {fullRoute.length > 1 && (
          <circle r="7" fill="#fff" filter="url(#glow)">
            <animateMotion dur="3s" repeatCount="indefinite" path={pathD(fullRoute)} />
          </circle>
        )}

        {/* Decision banner */}
        <g>
          <rect x="24" y="24" width="300" height="86" rx="10" fill="#000000" opacity="0.55" />
          <text x="44" y="58" fill="#ffffff" opacity="0.7" fontSize="14" letterSpacing="3">AI UMPIRE DECISION</text>
          <text x="44" y="94" fill={dColor} fontSize="34" fontWeight="900" letterSpacing="1">{decision}</text>
        </g>

        {/* Confidence */}
        <g>
          <rect x={W - 224} y="24" width="200" height="86" rx="10" fill="#000000" opacity="0.55" />
          <text x={W - 204} y="58" fill="#ffffff" opacity="0.7" fontSize="14" letterSpacing="3">CONFIDENCE</text>
          <text x={W - 204} y="94" fill="#ffffff" fontSize="34" fontWeight="900">{analysis.confidence ?? '—'}%</text>
        </g>

        {/* Legend */}
        <g fontSize="13" fill="#ffffff" opacity="0.75">
          <line x1="30" y1={H - 52} x2="70" y2={H - 52} stroke="#ffffff" strokeWidth="3" />
          <text x="80" y={H - 47}>Tracked path</text>
          <line x1="210" y1={H - 52} x2="250" y2={H - 52} stroke={dColor} strokeWidth="3" strokeDasharray="8 5" />
          <text x="260" y={H - 47}>Predicted path</text>
        </g>
      </svg>
    </div>
  );
}

export default HawkEyeVisualizer;

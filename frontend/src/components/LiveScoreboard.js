import React from 'react';

/**
 * LiveScoreboard — broadcast-style live score display (P1).
 * TV par jaisa dikhta hai!
 */
function LiveScoreboard({ live }) {
  if (!live || !live.live) {
    return (
      <div style={styles.container}>
        <div style={styles.noLive}>Koi live match nahi</div>
      </div>
    );
  }

  const l = live.live;
  const drsActive = l.drs && l.drs.status === 'review_pending';

  return (
    <div style={styles.container}>
      {/* Top bar: teams + score */}
      <div style={styles.scorebar}>
        <div style={styles.team}>
          <span style={styles.teamName}>{live.team_a_name}</span>
          <span style={styles.score}>
            {l.total_runs}/{l.total_wickets}
          </span>
          <span style={styles.overs}>({l.total_overs} ov)</span>
        </div>
        <div style={styles.vs}>vs</div>
        <div style={styles.team}>
          <span style={styles.teamName}>{live.team_b_name}</span>
        </div>
      </div>

      {/* Run rate */}
      <div style={styles.rates}>
        <span>RR: <b>{l.run_rate}</b></span>
      </div>

      {/* DRS status banner */}
      {drsActive && (
        <div style={styles.drsBanner}>
          🔍 DRS REVIEW PENDING ({l.drs.pending_reviews})
        </div>
      )}

      {/* Recent balls */}
      <div style={styles.ballsSection}>
        <div style={styles.sectionTitle}>Recent Balls</div>
        <div style={styles.balls}>
          {(l.recent_balls || []).map((b, i) => (
            <div
              key={i}
              style={{
                ...styles.ball,
                backgroundColor: b.is_wicket ? '#ef4444'
                  : b.runs_off_bat === 4 ? '#f97316'
                  : b.runs_off_bat === 6 ? '#a855f7'
                  : b.runs_off_bat === 0 ? '#374151' : '#22c55e',
              }}
            >
              {b.is_wicket ? 'W' : b.total_runs}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: '#0f172a', color: '#fff', borderRadius: 12,
    padding: 16, fontFamily: 'system-ui', maxWidth: 600,
  },
  noLive: { textAlign: 'center', padding: 20, opacity: 0.6 },
  scorebar: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: '#1e3a5f', borderRadius: 8, padding: '12px 16px',
  },
  team: { display: 'flex', alignItems: 'baseline', gap: 8 },
  teamName: { fontWeight: 'bold', fontSize: 16 },
  score: { fontSize: 28, fontWeight: 'bold', color: '#fbbf24' },
  overs: { opacity: 0.7, fontSize: 14 },
  vs: { opacity: 0.5, fontSize: 12 },
  rates: { marginTop: 8, fontSize: 14, opacity: 0.9 },
  drsBanner: {
    marginTop: 12, backgroundColor: '#7c3aed', borderRadius: 8,
    padding: 10, textAlign: 'center', fontWeight: 'bold',
    animation: 'pulse 1.5s infinite',
  },
  ballsSection: { marginTop: 12 },
  sectionTitle: { fontSize: 12, opacity: 0.6, marginBottom: 6 },
  balls: { display: 'flex', gap: 6, flexWrap: 'wrap' },
  ball: {
    width: 32, height: 32, borderRadius: '50%', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
    fontWeight: 'bold', fontSize: 13,
  },
};

export default LiveScoreboard;

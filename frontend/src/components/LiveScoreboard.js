import React from 'react';

/**
 * LiveScoreboard — broadcast-style live score display (P1).
 * TV par jaisa dikhta hai!
 */
function LiveScoreboard({ live, innings }) {
  if (!live || !live.live) {
    return (
      <div style={styles.container}>
        <div style={styles.noLive}>Koi live match nahi</div>
      </div>
    );
  }

  const l = live.live;
  const drsActive = l.drs && l.drs.status === 'review_pending';

  // FE-H3: pehle innings totals hamesha team_a_name ke neeche dikhte
  // the, team_b ka score kabhi nahi — Team B batting kar rahi ho to
  // score galat team ke naam par dikhta tha. Ab batting team
  // batting_team_id se pehchano (team_a_id/team_b_id se match karke).
  const battingTeamId = l.batting_team_id;
  const battingName =
    battingTeamId === live.team_a_id ? live.team_a_name
    : battingTeamId === live.team_b_id ? live.team_b_name
    : live.team_a_name;
  const otherName =
    battingName === live.team_a_name ? live.team_b_name : live.team_a_name;
  const otherTeamId =
    battingTeamId === live.team_a_id ? live.team_b_id : live.team_a_id;
  // Dono teams ke scores: /live sirf current innings deta hai, isliye
  // doosri innings ka score match detail (innings prop) se lo, jab
  // mile; na mile to score mat gado — "yet to bat" dikhao.
  const otherInnings = Array.isArray(innings)
    ? innings.find((i) => i.batting_team_id === otherTeamId)
    : null;

  return (
    <div style={styles.container}>
      {/* Top bar: teams + score — batting team pehle, uska score usi
          ke naam ke neeche; doosri team ka score bhi jab maujood ho */}
      <div style={styles.scorebar}>
        <div style={styles.team}>
          <span style={styles.teamName}>{battingName} (batting)</span>
          <span style={styles.score}>
            {l.total_runs}/{l.total_wickets}
          </span>
          <span style={styles.overs}>({l.total_overs} ov)</span>
        </div>
        <div style={styles.vs}>vs</div>
        <div style={styles.team}>
          <span style={styles.teamName}>{otherName}</span>
          {otherInnings ? (
            <>
              <span style={styles.score}>
                {otherInnings.total_runs}/{otherInnings.total_wickets}
              </span>
              <span style={styles.overs}>({otherInnings.total_overs} ov)</span>
            </>
          ) : (
            <span style={styles.overs}>yet to bat</span>
          )}
        </div>
      </div>

      {/* Run rate */}
      <div style={styles.rates}>
        <span>RR: <b>{l.run_rate}</b></span>
      </div>

      {/* FE-M8: striker / non-striker / bowler — backend ab
          batters_detail/bowlers_detail bhar deta hai (pehle khaali
          rehta tha, aur UI me slot hi nahi tha). */}
      {(l.batters_detail?.length > 0 || l.bowlers_detail?.length > 0) && (
        <div style={styles.players}>
          {(l.batters_detail || []).map((b) => (
            <span key={b.player_id || b.name}>
              {b.role === 'striker' ? '🏏 ' : ''}{b.name} ({b.role})
            </span>
          ))}
          {(l.bowlers_detail || []).map((b) => (
            <span key={b.player_id || b.name}>🎳 {b.name} ({b.role})</span>
          ))}
        </div>
      )}

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
  players: { marginTop: 8, fontSize: 13, opacity: 0.9, display: 'flex', gap: 12, flexWrap: 'wrap' },
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

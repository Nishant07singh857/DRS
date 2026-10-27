import React from 'react';
import { isUmpiresCall } from '../api/apiService';

/**
 * DRSReviewScreen — umpire review screen (P2).
 * 3D trajectory + evidence + decision panel.
 */
function DRSReviewScreen({ review }) {
  if (!review) {
    return <div style={styles.empty}>Review select karo</div>;
  }

  const statusColor = {
    pending: '#f59e0b', processing: '#3b82f6', completed: '#22c55e',
    inconclusive: '#eab308', confirmed: '#10b981', failed: '#ef4444',
  }[review.status] || '#6b7280';

  // FE-H2: pehle Final Decision sirf locked review par dikhta tha,
  // baaki par hamesha "Pending…" — jabki review.decision (pipeline
  // review ka AI decision) pehle se maujood tha. Ab: locked ho to
  // final_decision; warna final_decision, phir decision (PENDING
  // chhodkar), aur tabhi "Pending…" jab koi decision hi nahi hai.
  // AI Recommendation box bhi decision se fallback leta hai taaki
  // legacy review "..." na dikhaye.
  const shownDecision =
    review.final_decision ||
    (review.decision && review.decision !== 'PENDING' ? review.decision : null);
  const shownAi =
    review.ai_recommendation || shownDecision;
  const decisionColor = {
    'OUT': '#ef4444', 'NOT OUT': '#22c55e', 'INCONCLUSIVE': '#eab308',
  }[review.final_decision || shownAi] || '#fff';
  const umpiresCall = isUmpiresCall(review);
  const overlaps = review.analysis_data?.overlap_fractions || null;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.type}>{review.review_type} REVIEW</span>
        <span style={{ ...styles.status, backgroundColor: statusColor }}>
          {(review.status || 'unknown').toUpperCase()}
        </span>
      </div>

      {/* Original call vs AI */}
      <div style={styles.vsRow}>
        <div style={styles.callBox}>
          <div style={styles.label}>On-field Call</div>
          <div style={styles.call}>{review.original_call || '—'}</div>
        </div>
        <div style={styles.arrow}>→</div>
        <div style={styles.callBox}>
          <div style={styles.label}>AI Recommendation</div>
          <div style={styles.call}>{shownAi || '...'}</div>
          {review.ai_confidence != null && (
            <div style={styles.conf}>{review.ai_confidence}% confident</div>
          )}
        </div>
        <div style={styles.arrow}>→</div>
        <div style={{ ...styles.callBox, borderColor: decisionColor }}>
          <div style={styles.label}>Final Decision</div>
          <div style={{ ...styles.call, color: decisionColor }}>
            {review.is_locked ? (review.final_decision || '—') : (shownDecision || 'Pending...')}
          </div>
          {!review.is_locked && shownDecision && !review.final_decision && (
            <div style={styles.conf}>AI decision — umpire confirm karega</div>
          )}
          {review.is_locked && <div style={styles.locked}>🔒 LOCKED</div>}
        </div>
      </div>

      {/* FE-H7: Umpire's Call — backend decision string me kabhi nahi
          aata, sirf umpires_call flag me. Clear OUT/NOT OUT se alag
          dikhao: on-field decision stands. */}
      {umpiresCall && (
        <div style={styles.umpiresCall}>
          ⚖️ UMPIRE'S CALL — on-field decision stands
          {overlaps && (
            <span style={styles.overlaps}>
              {' '}
              (overlap: pitching {overlaps.pitch ?? '—'}, impact {overlaps.impact ?? '—'}, hitting {overlaps.hitting ?? '—'})
            </span>
          )}
        </div>
      )}

      {/* Evidence */}
      {review.evidence && Object.keys(review.evidence).length > 0 && (
        <div style={styles.evidence}>
          <div style={styles.label}>Evidence</div>
          <pre style={styles.pre}>
            {JSON.stringify(review.evidence, null, 2)}
          </pre>
        </div>
      )}

      {/* Confirmation note */}
      {review.confirmation_note && (
        <div style={styles.note}>
          📝 Umpire note: {review.confirmation_note}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: '#0f172a', color: '#fff', borderRadius: 12,
    padding: 20, fontFamily: 'system-ui', maxWidth: 700,
  },
  empty: { padding: 40, textAlign: 'center', opacity: 0.5 },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 16,
  },
  type: { fontSize: 20, fontWeight: 'bold' },
  status: {
    padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 'bold',
  },
  vsRow: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 },
  callBox: {
    flex: 1, backgroundColor: '#1e293b', borderRadius: 8, padding: 12,
    textAlign: 'center', border: '2px solid transparent',
  },
  label: { fontSize: 11, opacity: 0.6, marginBottom: 4 },
  call: { fontSize: 22, fontWeight: 'bold' },
  conf: { fontSize: 12, opacity: 0.7, marginTop: 4 },
  arrow: { fontSize: 20, opacity: 0.5 },
  locked: { fontSize: 11, color: '#10b981', marginTop: 4, fontWeight: 'bold' },
  umpiresCall: {
    marginBottom: 16, backgroundColor: '#78350f', border: '1px solid #f59e0b',
    borderRadius: 8, padding: 10, fontSize: 13, fontWeight: 'bold', color: '#fde68a',
  },
  overlaps: { fontWeight: 'normal', opacity: 0.85 },
  evidence: { backgroundColor: '#1e293b', borderRadius: 8, padding: 12 },
  pre: { fontSize: 12, overflow: 'auto', margin: 0 },
  note: {
    marginTop: 12, backgroundColor: '#1e3a5f', borderRadius: 8,
    padding: 10, fontSize: 13,
  },
};

export default DRSReviewScreen;

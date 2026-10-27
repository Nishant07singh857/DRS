import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getLiveMatch, getMatch } from '../api/apiService';
import LiveScoreboard from '../components/LiveScoreboard';

/**
 * LiveMatch — live match center page.
 * LiveScoreboard dikhata hai + har 10 second me auto-refresh.
 */
function LiveMatch() {
  const { matchId } = useParams();
  const [live, setLive] = useState(null);
  const [matchDetail, setMatchDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback((silent) => {
    if (!silent) setLoading(true);
    getLiveMatch(matchId)
      .then((response) => {
        setLive(response.data);
        setLastUpdated(new Date());
        setError('');
      })
      .catch(() => setError('Live data load nahi ho paya.'))
      .finally(() => setLoading(false));
    // FE-H3 (dono teams ke scores): match detail se innings totals
    // lo; fail ho to live scoreboard bina iske bhi chalta hai.
    getMatch(matchId)
      .then((response) => setMatchDetail(response.data))
      .catch(() => setMatchDetail(null));
  }, [matchId]);

  useEffect(() => {
    load(false);
    const timer = setInterval(() => load(true), 10000); // 10s auto-refresh
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div className="container mx-auto max-w-4xl">
      <div className="flex items-center justify-between mt-2 mb-6">
        <Link to="/" className="text-indigo-400 hover:underline">&larr; Home</Link>
        {lastUpdated && (
          <span className="text-xs text-gray-500">
            Updated: {lastUpdated.toLocaleTimeString()} · auto-refresh 10s
          </span>
        )}
      </div>

      <h1 className="text-3xl font-bold mb-6">Live Match Center</h1>

      {loading && <div className="text-center mt-10">Live score load ho raha hai...</div>}
      {!loading && error && <div className="text-center mt-10 text-red-500">{error}</div>}
      {!loading && !error && <LiveScoreboard live={live} innings={matchDetail?.innings} />}

      {!loading && !error && live && live.live && live.live.drs && (
        <div className="mt-6 text-center">
          {/* FE-H1: Phase 3 ke baad /live drs.review_id deta hai
              (latest pending/processing review, ya null) — pehle ye
              key thi hi nahi, isliye link hamesha /reviews par girta
              tha. review_id ho to seedha us review ke ReviewCenter
              par jao, warna saaf fallback text ke saath /reviews. */}
          {live.live.drs.review_id ? (
            <Link
              to={`/review/${live.live.drs.review_id}`}
              className="inline-block bg-amber-600 hover:bg-amber-500 text-white font-bold py-2 px-6 rounded-lg"
            >
              🔍 Review Center Kholo (Review #{live.live.drs.review_id})
            </Link>
          ) : (
            <Link
              to="/reviews"
              className="inline-block bg-gray-700 hover:bg-gray-600 text-white font-bold py-2 px-6 rounded-lg"
            >
              🔍 Reviews Dekho (koi pending review nahi)
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

export default LiveMatch;

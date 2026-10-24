import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getLiveMatch } from '../api/apiService';
import LiveScoreboard from '../components/LiveScoreboard';

/**
 * LiveMatch — live match center page.
 * LiveScoreboard dikhata hai + har 10 second me auto-refresh.
 */
function LiveMatch() {
  const { matchId } = useParams();
  const [live, setLive] = useState(null);
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
      {!loading && !error && <LiveScoreboard live={live} />}

      {!loading && !error && live && live.live && live.live.drs && (
        <div className="mt-6 text-center">
          <Link
            to={live.live.drs.review_id ? `/review/${live.live.drs.review_id}` : '/reviews'}
            className="inline-block bg-amber-600 hover:bg-amber-500 text-white font-bold py-2 px-6 rounded-lg"
          >
            🔍 Review Center Kholo
          </Link>
        </div>
      )}
    </div>
  );
}

export default LiveMatch;

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getReviewById, getBookmarks, fetchReviewVideoObjectUrl, reviewVideoBasename, reviewVideoUrl } from '../api/apiService';
import api from '../api/apiService';
import VideoReviewPlayer from '../components/VideoReviewPlayer';
import DRSReviewScreen from '../components/DRSReviewScreen';
import HawkEyeVisualizer from '../components/HawkEyeVisualizer';

/**
 * ReviewCenter — third umpire ka control room.
 * Ek screen par sab kuch:
 *  - VideoReviewPlayer: slow-mo / frame-step / zoom se video check
 *  - HawkEyeVisualizer: ball trajectory (broadcast style)
 *  - DRSReviewScreen: AI recommendation + on-field call
 *  - Umpire actions: Accept / Reject / Override (lock ke saath)
 */
function ReviewCenter() {
  const { id } = useParams();
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [acting, setActing] = useState(false);
  const [actionMsg, setActionMsg] = useState('');
  const [overrideDecision, setOverrideDecision] = useState('OUT');
  const [note, setNote] = useState('');
  const [showOverride, setShowOverride] = useState(false);
  // FE-C1: video blob object URL (JWT route ko <video> seedha nahi
  // khol sakta — Bearer header chahiye, isliye axios blob fetch).
  const [videoObjectUrl, setVideoObjectUrl] = useState(null);
  const [videoError, setVideoError] = useState('');
  // FE-M3: bookmarks pehle hamesha [] the; match-linked review par
  // backend se lao, warna khaali (upload review ka match_id null).
  const [bookmarks, setBookmarks] = useState([]);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getReviewById(id)
      .then((response) => setReview(response.data))
      .catch(() => setError('Review load nahi ho paya.'))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!review) return;
    if (review.match_id) {
      getBookmarks(review.match_id)
        .then((res) => setBookmarks(Array.isArray(res.data) ? res.data : []))
        .catch(() => setBookmarks([]));
    } else {
      setBookmarks([]);
    }
  }, [review]);

  useEffect(() => {
    let objectUrl = null;
    let cancelled = false;
    // FE-C1: bare server path (jaise /app/uploads/…) ab playable
    // NAHI mana jata — reviewVideoBasename us par null deta hai,
    // isliye player ki jagah saaf "video nahi mili" message aata hai,
    // HTML khilane wala silent fail nahi. Direct http(s) URL ho to
    // use seedha player ko do (blob fetch ki zaroorat nahi).
    const rawUrl = reviewVideoUrl(review);
    if (review && rawUrl && /^https?:\/\//i.test(rawUrl)) {
      setVideoObjectUrl(rawUrl);
      setVideoError('');
    } else if (review && reviewVideoBasename(review)) {
      fetchReviewVideoObjectUrl(review)
        .then((url) => {
          if (cancelled) {
            if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
            return;
          }
          objectUrl = url;
          setVideoObjectUrl(url);
          setVideoError(url ? '' : 'Is review ke liye playable video nahi mili.');
        })
        .catch(() => {
          if (!cancelled) setVideoError('Video load nahi ho payi — access ya file missing ho sakti hai.');
        });
    }
    return () => {
      cancelled = true;
      if (objectUrl && objectUrl.startsWith('blob:')) URL.revokeObjectURL(objectUrl);
    };
  }, [review]);

  const doAction = (action, finalDecision) => {
    setActing(true);
    setActionMsg('');
    const body = { action, note };
    if (action === 'override') body.final_decision = finalDecision;
    api.post(`/reviews/${id}/confirm`, body)
      .then(() => {
        setActionMsg('Decision lock ho gaya. ✅');
        setShowOverride(false);
        setNote('');
        load(); // taaza data
      })
      .catch((e) => {
        setActionMsg(e.response?.data?.message || 'Action fail ho gaya.');
      })
      .finally(() => setActing(false));
  };

  if (loading) return <div className="text-center mt-10">Review Center load ho raha hai...</div>;
  if (error) return <div className="text-center mt-10 text-red-500">{error}</div>;
  if (!review) return <div className="text-center mt-10">Review not found.</div>;

  const analysis = review.analysis_data || {};
  // FE-H2: Phase 3 ke baad pipeline reviews 'completed' (ya
  // 'inconclusive') + ai_recommendation ke saath bante hain, isliye
  // ye gate ab upload flow par bhi khulta hai — pehle status
  // default 'pending' + ai_recommendation NULL tha, isliye kabhi
  // nahi khulta tha. Confirm endpoint khud bhi completed/
  // inconclusive maangta hai, isliye gate ko usse alag mat karo:
  // pending/processing review par actions dikhane ki jagah saaf
  // wajah dikhao (neeche), taaki decided review undecided na lage.
  const canDecide =
    !review.is_locked &&
    (review.status === 'completed' || review.status === 'inconclusive');
  // Backend INCONCLUSIVE accept nahi karta (valid final decision
  // nahi) — accept button ko disabled + wajah ke saath dikhao,
  // taaki click par 400 ka surprise na ho.
  const acceptBlocked = review.ai_recommendation === 'INCONCLUSIVE';

  return (
    <div className="container mx-auto max-w-7xl">
      <Link to="/reviews" className="text-indigo-400 hover:underline">&larr; Reviews par wapas</Link>

      <div className="flex flex-col md:flex-row md:items-end justify-between gap-2 mt-4 mb-6">
        <div>
          <h1 className="text-4xl font-bold">Review Center</h1>
          <p className="text-gray-400 mt-1">
            Review #{review.id} · {review.review_type || 'LBW'} ·{' '}
            {review.created_at ? new Date(review.created_at).toLocaleString() : ''}
          </p>
        </div>
        {review.is_locked && (
          <span className="text-sm font-bold px-4 py-2 rounded-lg bg-emerald-900 text-emerald-300 border border-emerald-700">
            🔒 LOCKED — {review.final_decision}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: video + trajectory */}
        <div className="lg:col-span-2 space-y-6">
          {videoObjectUrl ? (
            <VideoReviewPlayer videoUrl={videoObjectUrl} bookmarks={bookmarks} fps={30} />
          ) : (
            <div className="bg-gray-800 rounded-xl p-8 text-center text-gray-500">
              {videoError || 'Is review ke liye playable video nahi mili.'}
              <div className="text-xs mt-2 text-gray-600">
                ({review.video_url || review.video_path || 'koi video path nahi'})
              </div>
            </div>
          )}

          <div>
            <h2 className="text-xl font-semibold mb-3">Ball Trajectory (Hawk-Eye)</h2>
            <HawkEyeVisualizer analysis={analysis} />
          </div>
        </div>

        {/* Right: AI screen + umpire actions */}
        <div className="space-y-6">
          <DRSReviewScreen review={review} />

          {canDecide && (
            <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
              <h3 className="text-lg font-semibold mb-3">Umpire Decision</h3>
              {acceptBlocked && (
                <p className="text-sm text-amber-300 mb-3">
                  AI recommendation INCONCLUSIVE hai — accept valid final decision nahi hai; reject ya override karo.
                </p>
              )}
              <div className="flex flex-col gap-2">
                <button
                  disabled={acting || acceptBlocked}
                  onClick={() => doAction('accept')}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold py-2 px-4 rounded-lg"
                >
                  ✅ AI Accept Karo
                </button>
                <button
                  disabled={acting}
                  onClick={() => doAction('reject')}
                  className="bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white font-bold py-2 px-4 rounded-lg"
                >
                  ❌ Reject — Original Call Wapas
                </button>
                <button
                  disabled={acting}
                  onClick={() => setShowOverride(!showOverride)}
                  className="bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-bold py-2 px-4 rounded-lg"
                >
                  ⚖️ Override Karo
                </button>
              </div>

              {showOverride && (
                <div className="mt-4 space-y-3 border-t border-gray-700 pt-4">
                  <div className="flex gap-2">
                    {['OUT', 'NOT OUT'].map((d) => (
                      <button
                        key={d}
                        onClick={() => setOverrideDecision(d)}
                        className={`flex-1 py-2 rounded-lg font-bold border ${
                          overrideDecision === d
                            ? 'bg-indigo-600 border-indigo-400 text-white'
                            : 'bg-gray-700 border-gray-600 text-gray-300'
                        }`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Kyun override kiya? (note)"
                    className="w-full bg-gray-700 rounded-lg p-2 text-sm text-white"
                    rows={2}
                  />
                  <button
                    disabled={acting}
                    onClick={() => doAction('override', overrideDecision)}
                    className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold py-2 px-4 rounded-lg"
                  >
                    Lock Karo: {overrideDecision}
                  </button>
                </div>
              )}

              {actionMsg && (
                <p className="mt-3 text-sm text-gray-300">{actionMsg}</p>
              )}
              <p className="mt-2 text-xs text-gray-500">
                Decision ke baad review lock ho jayega — badla nahi ja sakta.
              </p>
            </div>
          )}

          {!canDecide && !review.is_locked && (
            <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
              <h3 className="text-lg font-semibold mb-2">Umpire Decision</h3>
              <p className="text-sm text-gray-400">
                Umpire actions is review par abhi available nahi hain — status
                '{review.status || 'unknown'}' hai; confirm ke liye status
                'completed' ya 'inconclusive' hona chahiye.
                {review.decision && review.decision !== 'PENDING' && (
                  <> Upar dikhaya gaya AI decision ({review.decision}) abhi final/locked nahi hai.</>
                )}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ReviewCenter;

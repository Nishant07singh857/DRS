import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../App';

const FEATURES = [
  {
    title: 'AI Ball Tracking',
    text: 'YOLOv8 se ball, pad aur bat ka frame-by-frame detection. Custom cricket model lagao ya built-in fallback se shuru karo.',
  },
  {
    title: 'Deterministic Decisions',
    text: 'Koi coin-flip nahi. Trajectory extrapolation se OUT / NOT OUT / Umpire\u2019s Call — same video par hamesha same faisla.',
  },
  {
    title: 'Broadcast Graphics',
    text: 'Hawk-Eye style visualization — pitch point, impact, predicted path aur confidence, TV jaisi clarity ke saath.',
  },
  {
    title: 'Built to Scale',
    text: 'Celery background workers, TimescaleDB aur Docker Compose — ek video se lekar poori tournament feed tak.',
  },
];

const STEPS = [
  { n: '1', title: 'Video upload karo', text: 'Match ka LBW clip upload karo. Processing background me chalti hai.' },
  { n: '2', title: 'AI track karta hai', text: 'Ball ki trajectory detect hoti hai, har frame par progress dikhta hai.' },
  { n: '3', title: 'Decision pao', text: 'OUT / NOT OUT confidence ke saath, plus poora visual breakdown.' },
];

function LandingPage() {
  const { user } = useAuth();

  return (
    <div className="-m-4 md:-m-8">
      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-b from-indigo-950 via-gray-900 to-gray-900 px-6 py-20 md:py-28 text-center">
        <div className="absolute inset-0 opacity-20 pointer-events-none"
          style={{ backgroundImage: 'radial-gradient(circle at 50% 30%, #4f46e5 0%, transparent 60%)' }} />
        <div className="relative max-w-4xl mx-auto">
          <p className="text-indigo-400 font-semibold tracking-[0.3em] text-sm mb-4">AI-POWERED CRICKET TECHNOLOGY</p>
          <h1 className="text-5xl md:text-7xl font-black text-white leading-tight">
            Every LBW.<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-emerald-400">
              Decided by Data.
            </span>
          </h1>
          <p className="text-gray-400 text-lg md:text-xl mt-6 max-w-2xl mx-auto">
            AI Umpire PRO-X match video se ball track karke LBW decision deta hai —
            Hawk-Eye jaisi visualization ke saath, deterministic aur repeatable.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
            {user ? (
              <>
                <Link to="/upload" className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-8 py-4 rounded-lg text-lg transition shadow-lg shadow-indigo-900">
                  Analyze a Video
                </Link>
                <Link to="/reviews" className="bg-gray-800 hover:bg-gray-700 text-white font-bold px-8 py-4 rounded-lg text-lg transition border border-gray-700">
                  My Reviews
                </Link>
              </>
            ) : (
              <>
                <Link to="/register" className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-8 py-4 rounded-lg text-lg transition shadow-lg shadow-indigo-900">
                  Get Started Free
                </Link>
                <Link to="/login" className="bg-gray-800 hover:bg-gray-700 text-white font-bold px-8 py-4 rounded-lg text-lg transition border border-gray-700">
                  Login
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 py-16 md:py-20 max-w-6xl mx-auto">
        <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">
          Broadcast-grade decision review
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {FEATURES.map((f) => (
            <div key={f.title} className="bg-gray-800/70 border border-gray-700 rounded-xl p-6 hover:border-indigo-500 transition">
              <h3 className="text-xl font-bold text-white mb-3">{f.title}</h3>
              <p className="text-gray-400 leading-relaxed">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 py-16 bg-gray-800/40 border-y border-gray-800">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">Kaise kaam karta hai</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {STEPS.map((s) => (
              <div key={s.n} className="text-center">
                <div className="w-14 h-14 mx-auto rounded-full bg-indigo-600 flex items-center justify-center text-2xl font-black text-white mb-4">
                  {s.n}
                </div>
                <h3 className="text-xl font-bold text-white mb-2">{s.title}</h3>
                <p className="text-gray-400">{s.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-20 text-center">
        <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Apna pehla review chalao</h2>
        <p className="text-gray-400 mb-8">Account banao, video upload karo, decision dekho — sab kuch minutes me.</p>
        <Link
          to={user ? '/upload' : '/register'}
          className="inline-block bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-10 py-4 rounded-lg text-lg transition shadow-lg shadow-indigo-900"
        >
          {user ? 'Upload Video' : 'Create Free Account'}
        </Link>
      </section>

      {/* Footer */}
      <footer className="px-6 py-8 border-t border-gray-800 text-center text-gray-500 text-sm">
        AI Umpire PRO-X — deterministic AI umpiring technology.
      </footer>
    </div>
  );
}

export default LandingPage;

import axios from 'axios';

// FE-M5: REACT_APP_API_URL se override ho sakta hai (bina rebuild ke
// backend badalne ke liye); warna production me same-origin '/api'
// (nginx proxy), dev me seedha backend.
const api = axios.create({
  baseURL:
    process.env.REACT_APP_API_URL ||
    (process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:5001/api'),
  // FE-M5: hung backend UI ko hamesha ke liye latka deta tha.
  // 5 min — bada upload bhi isme aa jata hai, hung request nahi.
  timeout: 300000,
});

// हर अनुरोध के साथ JWT टोकन भेजें
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const SESSION_EXPIRED_EVENT = 'drs:session-expired';

const isAuthPath = (url = '') =>
  url.includes('/auth/login') || url.includes('/auth/register');

// Response interceptor to handle authentication errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // FE-C2: pehle ye interceptor POST /auth/login par bhi chalta
      // tha — galat credentials par backend 401 deta, interceptor
      // full-page reload karke /login par phenkta, aur LoginPage ka
      // "Invalid credentials" message reload me mit jata tha. Ab
      // auth calls par interceptor kuch nahi karta; error calling
      // page (Login/Register) khud dikhata hai.
      if (isAuthPath(error.config?.url)) {
        return Promise.reject(error);
      }
      // FE-C2: window.location.href ki jagah — token hatao, App ko
      // event se batao jo router navigation + "session expired"
      // message dikhata hai. Koi full-page reload nahi, isliye
      // mid-flow UI state (jaise ReviewCenter ka note) bachta hai
      // jab tak App navigate nahi karta; navigate par hi state reset
      // hota hai, wo bhi message ke saath.
      localStorage.removeItem('accessToken');
      try {
        sessionStorage.setItem('sessionExpired', '1');
      } catch (e) {
        // sessionStorage unavailable ho to bhi error aage badhe
      }
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  }
);

// Authentication Calls
export const login = (credentials) => api.post('/auth/login', credentials);
export const register = (userData) => api.post('/auth/register', userData);
export const getProfile = () => api.get('/auth/profile');

// Analysis Calls
export const uploadVideo = (formData, onUploadProgress) => api.post('/analysis/upload', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
  onUploadProgress,
});

// Task Status
export const getTaskStatus = (taskId) => api.get(`/tasks/${taskId}/status`);

// Review Calls (paginated)
export const getUserReviews = (page = 1, perPage = 20) =>
  api.get('/reviews', { params: { page, per_page: perPage } });
export const getReviewById = (id) => api.get(`/reviews/${id}`);

// Live Match Center (D)
export const getLiveMatch = (matchId) => api.get(`/matches/${matchId}/live`);
export const getMatch = (matchId) => api.get(`/matches/${matchId}`);

// Replay bookmarks (ReviewCenter timeline markers, FE-M3)
export const getBookmarks = (matchId) =>
  api.get('/replay/bookmarks', { params: { match_id: matchId } });

// Pitch Map / Over Summary (FE-H6) — stateless transforms, koi DB
// row nahi; caller body me data deta hai.
export const getPitchMap = (body) => api.post('/reviews/pitch-map', body);
export const getOverSummary = (body) => api.post('/reviews/over-summary', body);

// ---- FE-C1: review video URL helpers ----
// Backend ab sirf basename deta hai (video_url = 'uuid.mp4', kabhi
// absolute server path nahi — Phase 1 SEC-M1). Purana guard
// startsWith('/') ko playable maanta tha, jabki '/app/uploads/…'
// browser ke liye koi URL hi nahi tha.
// Playable sirf tab:
//  - bare basename (koi '/' nahi) → /api/uploads/<basename>
//  - http(s) URL ya pehle se /api/uploads/… URL
//  - blob: URL (player ko di gayi fetched video)
// Bare server path (doosra '/' wala path) NOT playable hai.
export function reviewVideoBasename(review) {
  const raw = review?.video_url || review?.video_path || '';
  if (!raw || raw.includes('/') || raw.includes('\\')) return null;
  return raw;
}

export function reviewVideoUrl(review) {
  const basename = reviewVideoBasename(review);
  if (basename) {
    const base = (api.defaults.baseURL || '/api').replace(/\/$/, '');
    return `${base}/uploads/${encodeURIComponent(basename)}`;
  }
  const raw = review?.video_url || review?.video_path || '';
  if (/^(https?:)?\/\//i.test(raw) || raw.startsWith('/api/uploads/') || raw.startsWith('blob:')) {
    return raw;
  }
  return null;
}

// <video> tag Bearer header nahi bhejta, aur uploads route JWT
// maangta hai — isliye video axios se blob ki tarah fetch karke
// object URL banao. Caller ko URL.revokeObjectURL karna chahiye.
export async function fetchReviewVideoObjectUrl(review) {
  const url = reviewVideoUrl(review);
  if (!url) return null;
  if (url.startsWith('blob:') || /^https?:\/\//i.test(url)) return url;
  const res = await api.get(url, { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

// Umpire's Call (FE-H7): backend kabhi "UMPIRE'S CALL" decision string
// nahi deta — marginal call par on-field decision (OUT/NOT OUT)
// + umpires_call: true aata hai. Isi flag se badge dikhao.
export function isUmpiresCall(review, analysis) {
  const a = analysis || review?.analysis_data || {};
  return a.umpires_call === true;
}

export default api;

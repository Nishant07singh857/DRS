import React, { useState, createContext, useContext, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import * as api from './api/apiService';
import { SESSION_EXPIRED_EVENT } from './api/apiService';

// FE-M4: pehle koi error boundary nahi tha — ek malformed payload
// poora SPA whitescreen kar deta tha. Ab routes boundary ke andar.
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="text-center mt-10 text-white">
          <p className="text-red-400 font-bold">Kuch galat ho gaya — page load nahi ho paya.</p>
          <button
            className="mt-4 bg-indigo-600 px-4 py-2 rounded"
            onClick={() => window.location.reload()}
          >
            Page Reload Karo
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// FE-C2: interceptor ab window.location.href reload nahi karta —
// ye watcher event sunta hai, logout karta hai, aur router se
// /login par le jata hai, session-expired message ke saath.
function SessionExpiryWatcher() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  useEffect(() => {
    const handler = () => {
      logout();
      navigate('/login', { state: { sessionExpired: true } });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handler);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
  }, [logout, navigate]);
  return null;
}

// Pages
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import LandingPage from './pages/LandingPage';
import UploadPage from './pages/UploadPage';
import ReviewGalleryPage from './pages/ReviewGalleryPage';
import ReviewDetailPage from './pages/ReviewDetailPage';
import ReviewCenter from './pages/ReviewCenter';
import LiveMatch from './pages/LiveMatch';
import Header from './components/Header';

// 1. Auth Context बनाना और एक्सपोर्ट करना
export const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      api.getProfile().then(response => {
        setUser(response.data);
      }).catch((error) => {
        console.error('Profile fetch error:', error);
        localStorage.removeItem('accessToken');
      }).finally(() => {
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (credentials) => {
    try {
      const response = await api.login(credentials);
      localStorage.setItem('accessToken', response.data.access_token);
      const profileResponse = await api.getProfile();
      setUser(profileResponse.data);
      return { success: true };
    } catch (error) {
      // FE-M7: profile fetch fail ho to abhi store kiya token peeche
      // reh jata tha aur next mount phir usi se retry karta tha.
      localStorage.removeItem('accessToken');
      console.error('Login error:', error);
      return { success: false, message: error.response?.data?.message || 'Login failed' };
    }
  };
  
  const logout = () => {
    localStorage.removeItem('accessToken');
    setUser(null);
  };

  const authContextValue = { user, login, logout };

  if (loading) {
    return <div className="bg-gray-900 min-h-screen flex justify-center items-center text-white">Loading Application...</div>;
  }
  
  return (
    <AuthContext.Provider value={authContextValue}>
      <Router>
        <SessionExpiryWatcher />
        <div className="bg-gray-900 min-h-screen text-white">
          <Header />
          <main className="p-4 md:p-8">
            <ErrorBoundary>
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={!user ? <LoginPage /> : <Navigate to="/" />} />
              <Route path="/register" element={!user ? <RegisterPage /> : <Navigate to="/" />} />

              <Route path="/upload" element={user ? <UploadPage /> : <Navigate to="/login" />} />
              <Route path="/reviews" element={user ? <ReviewGalleryPage /> : <Navigate to="/login" />} />
              <Route path="/reviews/:id" element={user ? <ReviewDetailPage /> : <Navigate to="/login" />} />
              <Route path="/review/:id" element={user ? <ReviewCenter /> : <Navigate to="/login" />} />
              <Route path="/live/:matchId" element={user ? <LiveMatch /> : <Navigate to="/login" />} />

              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </Router>
    </AuthContext.Provider>
  );
}

export default App;
import React, { useState, createContext, useContext, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import * as api from './api/apiService';

// Pages
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import LandingPage from './pages/LandingPage';
import UploadPage from './pages/UploadPage';
import ReviewGalleryPage from './pages/ReviewGalleryPage';
import ReviewDetailPage from './pages/ReviewDetailPage';
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
        <div className="bg-gray-900 min-h-screen text-white">
          <Header />
          <main className="p-4 md:p-8">
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={!user ? <LoginPage /> : <Navigate to="/" />} />
              <Route path="/register" element={!user ? <RegisterPage /> : <Navigate to="/" />} />

              <Route path="/upload" element={user ? <UploadPage /> : <Navigate to="/login" />} />
              <Route path="/reviews" element={user ? <ReviewGalleryPage /> : <Navigate to="/login" />} />
              <Route path="/reviews/:id" element={user ? <ReviewDetailPage /> : <Navigate to="/login" />} />

              <Route path="*" element={<Navigate to="/" />} />
            </Routes>
          </main>
        </div>
      </Router>
    </AuthContext.Provider>
  );
}

export default App;
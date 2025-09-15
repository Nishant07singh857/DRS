import axios from 'axios';

const api = axios.create({
  baseURL: process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:5001/api',
});

// हर अनुरोध के साथ JWT टोकन भेजें
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor to handle authentication errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('accessToken');
      window.location.href = '/login';
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

// Review Calls
export const getUserReviews = () => api.get('/reviews');
export const getReviewById = (id) => api.get(`/reviews/${id}`);

export default api;
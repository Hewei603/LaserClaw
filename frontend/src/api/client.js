import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const formatErrorDetail = (detail) => {
  if (!detail) {
    return 'Request failed';
  }
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join('; ');
  }
  return detail.message || detail.error || JSON.stringify(detail);
};

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const detail = formatErrorDetail(error.response.data?.detail || error.response.statusText);
      return Promise.reject(new Error(`${error.response.status}: ${detail}`));
    }

    if (error.request) {
      return Promise.reject(
        new Error(
          `Cannot reach LaserClaw API at ${API_BASE_URL}. Check that the backend is running and CORS allows this browser origin.`,
        ),
      );
    }

    return Promise.reject(new Error(error.message || 'Unexpected API error'));
  },
);

export default apiClient;

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
      const statusHints = {
        400: '请求内容有误，请检查填写内容',
        401: '未授权，请检查登录状态或 API Key',
        403: '当前账号权限不足',
        404: '请求的内容不存在',
        422: '填写内容的格式不正确，请检查输入',
        500: '服务器内部错误，请稍后再试',
        502: 'AI 服务暂时不可用，请稍后再试',
      };
      const hint = statusHints[error.response.status];
      const detail = formatErrorDetail(error.response.data?.detail || error.response.statusText);
      console.error('API error', error.response.status, detail);
      return Promise.reject(new Error(hint ? `${hint}（${detail}）` : `${error.response.status}: ${detail}`));
    }

    if (error.request) {
      console.error('API unreachable', API_BASE_URL);
      return Promise.reject(new Error(`无法连接后端服务（${API_BASE_URL}），请确认后端已启动。`));
    }

    return Promise.reject(new Error(error.message || 'Unexpected API error'));
  },
);

export default apiClient;

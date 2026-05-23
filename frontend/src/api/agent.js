import apiClient from './client';

export const agentApi = {
  createTask: async ({ caseId, goal, mode = 'troubleshooting', requireCitations = true }) => {
    const response = await apiClient.post('/api/agent/tasks', {
      case_id: caseId,
      goal,
      mode,
      require_citations: requireCitations,
    });
    return response.data;
  },

  listTasks: async (caseId = null) => {
    const response = await apiClient.get('/api/agent/tasks', {
      params: caseId ? { case_id: caseId } : {},
    });
    return response.data;
  },

  getTask: async (taskId) => {
    const response = await apiClient.get(`/api/agent/tasks/${taskId}`);
    return response.data;
  },

  createSession: async ({ caseId = null, title = null } = {}) => {
    const response = await apiClient.post('/api/agent/sessions', {
      case_id: caseId,
      title,
    });
    return response.data;
  },

  listSessions: async (caseId = null) => {
    const response = await apiClient.get('/api/agent/sessions', {
      params: caseId ? { case_id: caseId } : {},
    });
    return response.data;
  },

  getSession: async (sessionId) => {
    const response = await apiClient.get(`/api/agent/sessions/${sessionId}`);
    return response.data;
  },

  listMessages: async (sessionId) => {
    const response = await apiClient.get(`/api/agent/sessions/${sessionId}/messages`);
    return response.data;
  },

  chat: async ({ message, caseId = null, sessionId = null, mode = 'auto' }) => {
    const response = await apiClient.post('/api/agent/chat', {
      session_id: sessionId,
      message,
      case_id: caseId,
      mode,
    });
    return response.data;
  },
};

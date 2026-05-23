import apiClient from './client';

export const knowledgeApi = {
  listSources: async (caseId = null) => {
    const response = await apiClient.get('/api/knowledge/sources', {
      params: caseId ? { case_id: caseId } : {},
    });
    return response.data;
  },

  search: async ({ query, caseId, topK = 5 }) => {
    const response = await apiClient.post('/api/knowledge/search', {
      query,
      case_id: caseId,
      top_k: topK,
    });
    return response.data;
  },

  uploadGlobalSource: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/api/knowledge/sources/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  deleteSource: async (sourceId) => {
    await apiClient.delete(`/api/knowledge/sources/${sourceId}`);
  },
};


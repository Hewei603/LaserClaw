import apiClient from './client';

export const workbenchApi = {
  getProject: async (id, revisionId) => (await apiClient.get(`/api/cases/${id}/optical-project`, { params: { revision_id: revisionId } })).data,
  saveProject: async (id, payload) => (await apiClient.post(`/api/cases/${id}/optical-project`, payload)).data,
  scanProject: async (id, revisionId, payload) => (await apiClient.post(`/api/cases/${id}/optical-project/${revisionId}/scan-2d`, payload)).data,
  get: async id => (await apiClient.get(`/api/cases/${id}/workbench`)).data,
  getRun: async (id, taskId) => (await apiClient.get(`/api/cases/${id}/workbench/runs/${taskId}`)).data,
  run: async (id, message, attachmentIds) => (await apiClient.post(`/api/cases/${id}/workbench/runs`, { message, attachment_ids: attachmentIds })).data,
  stop: async (id, taskId) => (await apiClient.post(`/api/cases/${id}/workbench/runs/${taskId}/stop`)).data,
};

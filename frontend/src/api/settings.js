import apiClient from './client';

export const getAgentSettings = () => apiClient.get('/api/settings/agent').then((res) => res.data);
export const saveAgentSettings = (settings) => apiClient.put('/api/settings/agent', settings).then((res) => res.data);
export const getCodexStatus = (path = '') => apiClient.get('/api/settings/agent/codex/status', {
  params: { executable_path: path },
}).then((res) => res.data);
export const testCodexConnection = (settings) => apiClient.post('/api/settings/agent/codex/test', settings).then((res) => res.data);

/**
 * 实验案例API
 */
import apiClient, { API_BASE_URL } from './client';

export const casesApi = {
  // 获取所有案例
  list: async (params = {}) => {
    const response = await apiClient.get('/api/cases', { params });
    return response.data;
  },

  // 获取单个案例
  get: async (id) => {
    const response = await apiClient.get(`/api/cases/${id}`);
    return response.data;
  },

  // 创建案例
  create: async (data) => {
    const response = await apiClient.post('/api/cases', data);
    return response.data;
  },

  // 更新案例
  update: async (id, data) => {
    const response = await apiClient.put(`/api/cases/${id}`, data);
    return response.data;
  },

  // 删除案例
  delete: async (id) => {
    await apiClient.delete(`/api/cases/${id}`);
  },

  // 生成实验计划
  generatePlan: async (id) => {
    const response = await apiClient.post(`/api/cases/${id}/generate-plan`);
    return response.data;
  },

  // 生成ReZonator模式
  generateRezonator: async (id) => {
    const response = await apiClient.post(`/api/cases/${id}/generate-rezonator`);
    return response.data;
  },

  // 生成故障排查
  generateTroubleshooting: async (id) => {
    const response = await apiClient.post(`/api/cases/${id}/generate-troubleshooting`);
    return response.data;
  },

  // 生成报告
  generateReport: async (id) => {
    const response = await apiClient.post(`/api/cases/${id}/generate-report`);
    return response.data;
  },

  // 获取生成的内容
  getGeneratedContents: async (id, contentType = null) => {
    const params = contentType ? { content_type: contentType } : {};
    const response = await apiClient.get(`/api/cases/${id}/generated-contents`, { params });
    return response.data;
  },

  // 上传附件
  uploadAttachment: async (id, file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post(`/api/cases/${id}/attachments`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // 获取附件列表
  listAttachments: async (id) => {
    const response = await apiClient.get(`/api/cases/${id}/attachments`);
    return response.data;
  },

  // 删除附件
  deleteAttachment: async (attachmentId) => {
    await apiClient.delete(`/api/attachments/${attachmentId}`);
  },

  analyzeAttachment: async (attachmentId) => {
    const response = await apiClient.post(`/api/attachments/${attachmentId}/analyze`);
    return response.data;
  },

  bundleUrl: (id) => `${API_BASE_URL}/api/cases/${id}/bundle`,
};

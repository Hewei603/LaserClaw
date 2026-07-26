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

  listModules: async (id) => {
    const response = await apiClient.get(`/api/cases/${id}/modules`);
    return response.data;
  },

  createModule: async (id, data) => {
    const response = await apiClient.post(`/api/cases/${id}/modules`, data);
    return response.data;
  },

  updateModule: async (moduleId, data) => {
    const response = await apiClient.patch(`/api/cases/modules/${moduleId}`, data);
    return response.data;
  },

  deleteModule: async (moduleId) => {
    await apiClient.delete(`/api/cases/modules/${moduleId}`);
  },

  uploadModuleFile: async (moduleId, file, fileRole = 'input') => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post(`/api/cases/modules/${moduleId}/files`, formData, {
      params: { file_role: fileRole },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  runModule: async (moduleId, data = {}) => {
    const response = await apiClient.post(`/api/cases/modules/${moduleId}/run`, data);
    return response.data;
  },

  listComponents: async (id, moduleId = null) => {
    const params = moduleId ? { module_id: moduleId } : {};
    const response = await apiClient.get(`/api/cases/${id}/components`, { params });
    return response.data;
  },

  createComponent: async (id, data) => {
    const response = await apiClient.post(`/api/cases/${id}/components`, data);
    return response.data;
  },

  updateComponent: async (itemId, data) => {
    const response = await apiClient.patch(`/api/cases/components/${itemId}`, data);
    return response.data;
  },

  deleteComponent: async (itemId) => {
    await apiClient.delete(`/api/cases/components/${itemId}`);
  },

  bundleUrl: (id) => `${API_BASE_URL}/api/cases/${id}/bundle`,
  moduleFileUrl: (fileId) => `${API_BASE_URL}/api/cases/module-files/${fileId}`,
  procurementUrl: (id) => `${API_BASE_URL}/api/cases/${id}/components/procurement.csv`,
};

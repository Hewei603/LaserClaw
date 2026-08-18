import apiClient from './client';

export const literatureApi = {
  search: async ({ query, yearFrom, maxResults, sort, sources }) => {
    const payload = { query };
    if (yearFrom) payload.year_from = Number(yearFrom);
    if (maxResults) payload.max_results = Number(maxResults);
    if (sort) payload.sort = sort;
    if (sources) payload.sources = sources;
    const response = await apiClient.post('/api/literature/search', payload);
    return response.data;
  },
};

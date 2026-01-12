/**
 * Cloud Cost Slayer - API Client
 */

import axios from 'axios';
import {
    DashboardStats,
    Recommendation,
    AnalysisRun,
    RecommendationFilters,
    ApiResponse
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE,
    headers: {
        'Content-Type': 'application/json',
    },
});

/**
 * Dashboard API
 */
export const dashboardApi = {
    // Get dashboard stats
    getStats: async (): Promise<DashboardStats> => {
        const response = await api.get<DashboardStats>('/api/stats');
        return response.data;
    },
};

/**
 * Analysis API
 */
export const analysisApi = {
    // Start a new analysis
    start: async (config?: {
        regions?: string[];
        excludeProduction?: boolean;
    }): Promise<AnalysisRun> => {
        const response = await api.post<AnalysisRun>('/api/analyze', config);
        return response.data;
    },

    // Get analysis status
    getStatus: async (id: string): Promise<AnalysisRun> => {
        const response = await api.get<AnalysisRun>(`/api/analyze/${id}`);
        return response.data;
    },

    // List recent analyses
    list: async (): Promise<AnalysisRun[]> => {
        const response = await api.get<AnalysisRun[]>('/api/analyses');
        return response.data;
    },
};

/**
 * Recommendations API
 */
export const recommendationsApi = {
    // List recommendations with filters
    list: async (filters?: RecommendationFilters): Promise<{
        recommendations: Recommendation[];
        total: number;
    }> => {
        const response = await api.get('/api/recommendations', { params: filters });
        return response.data;
    },

    // Get single recommendation
    get: async (id: string): Promise<Recommendation> => {
        const response = await api.get<Recommendation>(`/api/recommendations/${id}`);
        return response.data;
    },

    // Apply a recommendation
    apply: async (id: string, dryRun = false): Promise<{
        success: boolean;
        message: string;
    }> => {
        const response = await api.post(`/api/apply`, {
            recommendationIds: [id],
            dryRun,
        });
        return response.data;
    },

    // Dismiss a recommendation
    dismiss: async (id: string): Promise<{ success: boolean }> => {
        const response = await api.delete(`/api/recommendations/${id}`);
        return response.data;
    },
};

export default api;

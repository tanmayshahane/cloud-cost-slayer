/**
 * Cloud Cost Slayer - TypeScript Types
 */

// Recommendation types
export interface Recommendation {
    id: string;
    type: 'rightsizing' | 'scheduling' | 'reserved' | 'idle';
    instanceId: string;
    instanceName?: string;
    region: string;
    currentType: string;
    recommendedType?: string;
    monthlySavings: number;
    annualSavings: number;
    confidence: 'high' | 'medium' | 'low';
    currentCost: number;
    newCost: number;
    cpuAvg?: number;
    cpuMax?: number;
    status: 'pending' | 'applied' | 'dismissed';
}

// Instance types
export interface EC2Instance {
    instanceId: string;
    name: string;
    type: string;
    state: 'running' | 'stopped' | 'terminated';
    region: string;
    launchTime: string;
    runningDays: number;
    monthlyCost: number;
    cpuAvg: number;
    cpuMax: number;
    tags: Record<string, string>;
}

export interface RDSInstance {
    dbInstanceId: string;
    name: string;
    engine: string;
    engineVersion: string;
    instanceClass: string;
    region: string;
    multiAz: boolean;
    storageGb: number;
    monthlyCost: number;
    cpuAvg: number;
    connectionAvg: number;
}

// Analysis types
export interface AnalysisRun {
    id: string;
    status: 'running' | 'completed' | 'failed';
    progress: number;
    startedAt: string;
    completedAt?: string;
    regions: string[];
    instancesAnalyzed: number;
    recommendationsCount: number;
    totalSavings: number;
}

export interface AnalysisConfig {
    regions: string[];
    excludeTags: Record<string, string>;
    includeTags: Record<string, string>;
    excludeProduction: boolean;
    lookbackDays: number;
}

// Dashboard stats
export interface DashboardStats {
    totalCurrentSpend: number;
    totalPotentialSavings: number;
    optimizedSpend: number;
    savingsPercentage: number;
    instancesAnalyzed: number;
    recommendationsCount: number;
    highConfidenceCount: number;
    lastAnalysisAt?: string;
}

// Chart data types
export interface SavingsBreakdown {
    type: string;
    value: number;
    percentage: number;
    color: string;
}

export interface RegionalSavings {
    region: string;
    currentCost: number;
    potentialSavings: number;
}

// API response types
export interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    page: number;
    pageSize: number;
    hasMore: boolean;
}

// Filter types
export interface RecommendationFilters {
    type?: string;
    confidence?: string;
    minSavings?: number;
    region?: string;
    status?: string;
}

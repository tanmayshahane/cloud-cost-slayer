'use client';

import { useState, useEffect } from 'react';
import {
    Filter,
    TrendingDown,
    AlertTriangle,
    Activity,
    Server,
    Check,
    X,
    RefreshCw,
    PlayCircle
} from 'lucide-react';

interface Recommendation {
    id: string;
    type: string;
    instanceId: string;
    instanceName?: string;
    region: string;
    currentType: string;
    recommendedType?: string;
    monthlySavings: number;
    annualSavings: number;
    confidence: string;
    currentCost: number;
    newCost: number;
    cpuAvg?: number;
    cpuMax?: number;
    status: string;
}

export default function RecommendationsPage() {
    const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [typeFilter, setTypeFilter] = useState<string>('all');
    const [confidenceFilter, setConfidenceFilter] = useState<string>('all');
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchRecommendations();
    }, [typeFilter, confidenceFilter]);

    const fetchRecommendations = async () => {
        setIsLoading(true);
        try {
            const params = new URLSearchParams();
            if (typeFilter !== 'all') params.set('type', typeFilter);
            if (confidenceFilter !== 'all') params.set('confidence', confidenceFilter);

            const response = await fetch(`http://localhost:8000/api/recommendations?${params}`);
            if (response.ok) {
                const data = await response.json();
                setRecommendations(data.recommendations || []);
            } else {
                setRecommendations([]);
            }
        } catch (err) {
            setError('Failed to load recommendations');
            setRecommendations([]);
        } finally {
            setIsLoading(false);
        }
    };

    const totalSavings = recommendations.reduce((sum, rec) => sum + rec.monthlySavings, 0);

    const toggleSelect = (id: string) => {
        const newSelected = new Set(selectedIds);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        setSelectedIds(newSelected);
    };

    const selectAll = () => {
        if (selectedIds.size === recommendations.length) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(recommendations.map(r => r.id)));
        }
    };

    const applyRecommendation = async (id: string) => {
        try {
            const response = await fetch('http://localhost:8000/api/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recommendationIds: [id], dryRun: false }),
            });
            if (response.ok) {
                fetchRecommendations();
            }
        } catch (err) {
            console.error('Failed to apply recommendation');
        }
    };

    const dismissRecommendation = async (id: string) => {
        try {
            const response = await fetch(`http://localhost:8000/api/recommendations/${id}`, {
                method: 'DELETE',
            });
            if (response.ok) {
                fetchRecommendations();
            }
        } catch (err) {
            console.error('Failed to dismiss recommendation');
        }
    };

    const getTypeIcon = (type: string) => {
        switch (type) {
            case 'rightsizing': return <TrendingDown className="w-4 h-4" />;
            case 'idle': return <AlertTriangle className="w-4 h-4" />;
            case 'scheduling': return <Activity className="w-4 h-4" />;
            default: return <Server className="w-4 h-4" />;
        }
    };

    const getConfidenceColor = (confidence: string) => {
        switch (confidence) {
            case 'high': return 'text-green-600 bg-green-100';
            case 'medium': return 'text-yellow-600 bg-yellow-100';
            case 'low': return 'text-red-600 bg-red-100';
            default: return 'text-gray-600 bg-gray-100';
        }
    };

    const getTypeBadge = (type: string) => {
        const colors: Record<string, string> = {
            rightsizing: 'bg-blue-100 text-blue-700',
            idle: 'bg-red-100 text-red-700',
            scheduling: 'bg-purple-100 text-purple-700',
        };
        return colors[type] || 'bg-gray-100 text-gray-700';
    };

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <header className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white">
                <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold">Recommendations</h1>
                            <p className="mt-1 text-blue-100">Review and apply cost optimization recommendations</p>
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={fetchRecommendations}
                                className="flex items-center gap-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded-lg transition"
                            >
                                <RefreshCw className="w-4 h-4" />
                                Refresh
                            </button>
                            <a
                                href="/"
                                className="flex items-center gap-2 bg-white text-blue-600 px-4 py-2 rounded-lg hover:bg-blue-50 transition"
                            >
                                ← Dashboard
                            </a>
                        </div>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
                {/* Loading */}
                {isLoading && (
                    <div className="text-center py-12">
                        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin mx-auto mb-4" />
                        <p className="text-gray-600">Loading recommendations...</p>
                    </div>
                )}

                {/* Empty State */}
                {!isLoading && recommendations.length === 0 && (
                    <div className="text-center py-12 bg-white rounded-xl shadow-sm">
                        <Server className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                        <h2 className="text-xl font-semibold text-gray-900 mb-2">No Recommendations</h2>
                        <p className="text-gray-500 mb-6">Run an analysis first to get cost optimization recommendations.</p>
                        <a
                            href="/"
                            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                        >
                            <PlayCircle className="w-5 h-5" />
                            Go to Dashboard
                        </a>
                    </div>
                )}

                {/* Results */}
                {!isLoading && recommendations.length > 0 && (
                    <>
                        {/* Filters */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-6">
                            <div className="flex flex-wrap items-center gap-4">
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Filter className="w-4 h-4" />
                                    <span className="text-sm font-medium">Filters:</span>
                                </div>

                                <select
                                    value={typeFilter}
                                    onChange={(e) => setTypeFilter(e.target.value)}
                                    className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm"
                                >
                                    <option value="all">All Types</option>
                                    <option value="rightsizing">Rightsizing</option>
                                    <option value="idle">Idle</option>
                                    <option value="scheduling">Scheduling</option>
                                </select>

                                <select
                                    value={confidenceFilter}
                                    onChange={(e) => setConfidenceFilter(e.target.value)}
                                    className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm"
                                >
                                    <option value="all">All Confidence</option>
                                    <option value="high">High</option>
                                    <option value="medium">Medium</option>
                                    <option value="low">Low</option>
                                </select>

                                <div className="flex-1" />

                                <div className="text-sm text-gray-500">
                                    {recommendations.length} recommendation{recommendations.length !== 1 ? 's' : ''}
                                </div>

                                <div className="font-semibold text-green-600">
                                    ${totalSavings.toFixed(2)}/mo potential savings
                                </div>
                            </div>
                        </div>

                        {/* Bulk Actions */}
                        {selectedIds.size > 0 && (
                            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6 flex items-center justify-between">
                                <span className="text-blue-700">
                                    {selectedIds.size} recommendation(s) selected
                                </span>
                                <div className="flex gap-2">
                                    <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
                                        Apply Selected
                                    </button>
                                    <button
                                        onClick={() => setSelectedIds(new Set())}
                                        className="px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 text-sm"
                                    >
                                        Clear
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* List */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                            {/* Header */}
                            <div className="px-6 py-3 bg-gray-50 border-b border-gray-100 flex items-center gap-4 text-sm font-medium text-gray-500">
                                <input
                                    type="checkbox"
                                    checked={selectedIds.size === recommendations.length && recommendations.length > 0}
                                    onChange={selectAll}
                                    className="w-4 h-4 rounded"
                                />
                                <div className="flex-1">Instance</div>
                                <div className="w-24">Type</div>
                                <div className="w-24">Region</div>
                                <div className="w-28 text-right">Savings</div>
                                <div className="w-24 text-center">Confidence</div>
                                <div className="w-32 text-center">Actions</div>
                            </div>

                            {/* Rows */}
                            {recommendations.map(rec => (
                                <div
                                    key={rec.id}
                                    className="px-6 py-4 border-b border-gray-100 flex items-center gap-4 hover:bg-gray-50"
                                >
                                    <input
                                        type="checkbox"
                                        checked={selectedIds.has(rec.id)}
                                        onChange={() => toggleSelect(rec.id)}
                                        className="w-4 h-4 rounded"
                                    />

                                    <div className="flex-1">
                                        <p className="font-medium">{rec.instanceName || rec.instanceId}</p>
                                        <p className="text-sm text-gray-500">
                                            {rec.currentType}
                                            {rec.recommendedType && (
                                                <span> → <span className="text-green-600">{rec.recommendedType}</span></span>
                                            )}
                                        </p>
                                    </div>

                                    <div className="w-24">
                                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${getTypeBadge(rec.type)}`}>
                                            {getTypeIcon(rec.type)}
                                            {rec.type}
                                        </span>
                                    </div>

                                    <div className="w-24 text-sm text-gray-600">{rec.region}</div>

                                    <div className="w-28 text-right">
                                        <p className="font-bold text-green-600">${rec.monthlySavings.toFixed(2)}</p>
                                        <p className="text-xs text-gray-400">/month</p>
                                    </div>

                                    <div className="w-24 text-center">
                                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getConfidenceColor(rec.confidence)}`}>
                                            {rec.confidence}
                                        </span>
                                    </div>

                                    <div className="w-32 flex justify-center gap-2">
                                        <button
                                            onClick={() => applyRecommendation(rec.id)}
                                            className="p-2 bg-green-100 text-green-600 rounded-lg hover:bg-green-200"
                                            title="Apply"
                                        >
                                            <Check className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => dismissRecommendation(rec.id)}
                                            className="p-2 bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200"
                                            title="Dismiss"
                                        >
                                            <X className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </main>
        </div>
    );
}

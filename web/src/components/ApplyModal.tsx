'use client';

import { useState, useEffect } from 'react';
import { X, Play, RefreshCw, Zap, Server, Check, AlertTriangle } from 'lucide-react';

interface ApplyModalProps {
    isOpen: boolean;
    onClose: () => void;
    onComplete: () => void;
}

interface Recommendation {
    id: string;
    instanceId: string;
    instanceName?: string;
    currentType: string;
    recommendedType?: string;
    monthlySavings: number;
    type: string;
}

export default function ApplyModal({ isOpen, onClose, onComplete }: ApplyModalProps) {
    const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [action, setAction] = useState<'resize' | 'stop' | 'start'>('resize');
    const [dryRun, setDryRun] = useState(true);
    const [isLoading, setIsLoading] = useState(true);
    const [isApplying, setIsApplying] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (isOpen) {
            fetchRecommendations();
        }
    }, [isOpen]);

    const fetchRecommendations = async () => {
        setIsLoading(true);
        try {
            const response = await fetch('http://localhost:8000/api/recommendations');
            const data = await response.json();
            setRecommendations(data.recommendations || []);
        } catch (err) {
            setRecommendations([]);
        } finally {
            setIsLoading(false);
        }
    };

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

    const applyChanges = async () => {
        if (selectedIds.size === 0) return;

        setIsApplying(true);
        setError(null);
        setResult(null);

        try {
            const response = await fetch('http://localhost:8000/api/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    recommendationIds: Array.from(selectedIds),
                    action,
                    dryRun,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to apply changes');
            }

            const data = await response.json();
            setResult(data);

            if (!dryRun) {
                onComplete();
            }
        } catch (err: any) {
            setError(err.message || 'Failed to apply changes');
        } finally {
            setIsApplying(false);
        }
    };

    if (!isOpen) return null;

    const selectedSavings = recommendations
        .filter(r => selectedIds.has(r.id))
        .reduce((sum, r) => sum + r.monthlySavings, 0);

    return (
        <div className="fixed inset-0 z-50 overflow-y-auto">
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

            <div className="relative min-h-screen flex items-center justify-center p-4">
                <div className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
                    <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <Zap className="w-5 h-5 text-green-600" />
                            <h2 className="text-xl font-bold text-gray-900">Apply Recommendations</h2>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
                            <X className="w-5 h-5 text-gray-600" />
                        </button>
                    </div>

                    <div className="flex-1 overflow-y-auto p-6 space-y-6">
                        {/* Action Selection */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">Action</label>
                            <div className="flex gap-2">
                                {(['resize', 'stop', 'start'] as const).map(a => (
                                    <button
                                        key={a}
                                        onClick={() => setAction(a)}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium transition ${action === a ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                            }`}
                                    >
                                        {a.charAt(0).toUpperCase() + a.slice(1)}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Dry Run Toggle */}
                        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                            <label className="flex items-center gap-3 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={dryRun}
                                    onChange={() => setDryRun(!dryRun)}
                                    className="w-5 h-5 text-yellow-600 rounded"
                                />
                                <div>
                                    <span className="font-medium text-yellow-800">Dry Run Mode</span>
                                    <p className="text-sm text-yellow-700">
                                        {dryRun
                                            ? "Preview changes without making actual modifications"
                                            : "⚠️ Changes will be applied to AWS!"}
                                    </p>
                                </div>
                            </label>
                        </div>

                        {/* Recommendations List */}
                        <div>
                            <div className="flex items-center justify-between mb-3">
                                <label className="text-sm font-medium text-gray-700">
                                    Select Recommendations ({selectedIds.size} selected)
                                </label>
                                <button
                                    onClick={selectAll}
                                    className="text-sm text-blue-600 hover:text-blue-700"
                                >
                                    {selectedIds.size === recommendations.length ? 'Deselect All' : 'Select All'}
                                </button>
                            </div>

                            {isLoading ? (
                                <div className="text-center py-8">
                                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-gray-400" />
                                </div>
                            ) : recommendations.length === 0 ? (
                                <div className="text-center py-8 text-gray-500">
                                    <Server className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                    <p>No recommendations available</p>
                                    <p className="text-sm">Run an analysis first</p>
                                </div>
                            ) : (
                                <div className="space-y-2 max-h-64 overflow-y-auto">
                                    {recommendations.map(rec => (
                                        <div
                                            key={rec.id}
                                            onClick={() => toggleSelect(rec.id)}
                                            className={`p-3 rounded-lg border cursor-pointer transition ${selectedIds.has(rec.id)
                                                ? 'bg-green-50 border-green-300'
                                                : 'bg-white border-gray-200 hover:border-gray-300'
                                                }`}
                                        >
                                            <div className="flex items-center gap-3">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedIds.has(rec.id)}
                                                    onChange={() => { }}
                                                    className="w-4 h-4 text-green-600 rounded"
                                                />
                                                <div className="flex-1">
                                                    <p className="font-medium">{rec.instanceName || rec.instanceId}</p>
                                                    <p className="text-sm text-gray-500">
                                                        {rec.currentType}
                                                        {rec.recommendedType && ` → ${rec.recommendedType}`}
                                                    </p>
                                                </div>
                                                <span className="text-green-600 font-medium">
                                                    ${rec.monthlySavings.toFixed(2)}/mo
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Result */}
                        {result && (
                            <div className={`border rounded-lg p-4 ${result.dryRun ? 'bg-blue-50 border-blue-200' : 'bg-green-50 border-green-200'
                                }`}>
                                <p className="font-medium flex items-center gap-2">
                                    <Check className="w-5 h-5" />
                                    {result.dryRun ? 'Dry Run Complete' : 'Changes Applied'}
                                </p>
                                <p className="text-sm mt-1">
                                    {result.affectedInstances?.length || 0} instances affected
                                </p>
                                <p className="text-sm">
                                    Total Savings: ${result.totalSavings?.toFixed(2) || '0.00'}/month
                                </p>
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                                <p className="font-medium flex items-center gap-2">
                                    <AlertTriangle className="w-5 h-5" />
                                    Error
                                </p>
                                <p className="text-sm mt-1">{error}</p>
                            </div>
                        )}
                    </div>

                    <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t border-gray-100">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-sm text-gray-600">
                                Selected: {selectedIds.size} recommendation(s)
                            </span>
                            <span className="font-medium text-green-600">
                                ${selectedSavings.toFixed(2)}/mo savings
                            </span>
                        </div>
                        <button
                            onClick={applyChanges}
                            disabled={isApplying || selectedIds.size === 0}
                            className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isApplying || selectedIds.size === 0
                                ? 'bg-gray-300 text-gray-500'
                                : dryRun
                                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                                    : 'bg-green-600 text-white hover:bg-green-700'
                                }`}
                        >
                            {isApplying ? (
                                <>
                                    <RefreshCw className="w-5 h-5 animate-spin" />
                                    {dryRun ? 'Simulating...' : 'Applying...'}
                                </>
                            ) : (
                                <>
                                    <Zap className="w-5 h-5" />
                                    {dryRun ? 'Preview Changes (Dry Run)' : 'Apply Changes'}
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

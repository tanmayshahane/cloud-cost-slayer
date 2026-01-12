'use client';

import { useState } from 'react';
import { X, RefreshCw, FileText, Download, Eye, EyeOff } from 'lucide-react';

interface ReportModalProps {
    isOpen: boolean;
    onClose: () => void;
}

interface ReportResult {
    success: boolean;
    format: string;
    recommendationsCount: number;
    totalSavings: number;
    filepath: string;
    filename: string;
    content: string;
    message: string;
}

export default function ReportModal({ isOpen, onClose }: ReportModalProps) {
    const [format, setFormat] = useState<'html' | 'json' | 'markdown'>('html');
    const [confidence, setConfidence] = useState<string>('all');
    const [minSavings, setMinSavings] = useState(0);
    const [limit, setLimit] = useState(50);
    const [isGenerating, setIsGenerating] = useState(false);
    const [result, setResult] = useState<ReportResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showPreview, setShowPreview] = useState(true);

    const generateReport = async () => {
        setIsGenerating(true);
        setError(null);
        setResult(null);

        try {
            const response = await fetch('http://localhost:8000/api/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    format,
                    confidence: confidence === 'all' ? undefined : confidence,
                    minSavings,
                    limit,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to generate report');
            }

            const data = await response.json();
            setResult(data);
        } catch (err: any) {
            setError(err.message || 'Failed to generate report');
        } finally {
            setIsGenerating(false);
        }
    };

    const downloadReport = () => {
        if (!result) return;

        const blob = new Blob([result.content], {
            type: format === 'html' ? 'text/html' : format === 'json' ? 'application/json' : 'text/markdown'
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = result.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 overflow-y-auto">
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

            <div className="relative min-h-screen flex items-center justify-center p-4">
                <div className={`relative bg-white rounded-2xl shadow-2xl w-full ${result ? 'max-w-4xl' : 'max-w-lg'} transition-all`}>
                    <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between rounded-t-2xl">
                        <div className="flex items-center gap-3">
                            <FileText className="w-5 h-5 text-purple-600" />
                            <h2 className="text-xl font-bold text-gray-900">Generate Report</h2>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
                            <X className="w-5 h-5 text-gray-600" />
                        </button>
                    </div>

                    <div className="p-6 space-y-6">
                        {/* Configuration Section */}
                        <div className={`grid gap-6 ${result ? 'md:grid-cols-4' : ''}`}>
                            {/* Format */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Output Format</label>
                                <div className="flex gap-2">
                                    {(['html', 'json', 'markdown'] as const).map(f => (
                                        <button
                                            key={f}
                                            onClick={() => setFormat(f)}
                                            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${format === f ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                                }`}
                                        >
                                            {f.toUpperCase()}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Confidence Filter */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Confidence Level</label>
                                <select
                                    value={confidence}
                                    onChange={(e) => setConfidence(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
                                >
                                    <option value="all">All</option>
                                    <option value="high">High Only</option>
                                    <option value="medium">Medium & Above</option>
                                    <option value="low">Low & Above</option>
                                </select>
                            </div>

                            {/* Min Savings */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Min Savings ($)</label>
                                <input
                                    type="number"
                                    value={minSavings}
                                    onChange={(e) => setMinSavings(parseFloat(e.target.value) || 0)}
                                    min={0}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
                                />
                            </div>

                            {/* Limit */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Max Items</label>
                                <input
                                    type="number"
                                    value={limit}
                                    onChange={(e) => setLimit(parseInt(e.target.value) || 50)}
                                    min={1}
                                    max={500}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 bg-white"
                                />
                            </div>
                        </div>

                        {/* Result with Report Preview */}
                        {result && (
                            <div className="space-y-4">
                                {/* Success Message */}
                                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="font-medium text-green-800">✅ Report Generated</p>
                                            <p className="text-sm text-green-700 mt-1">
                                                {result.recommendationsCount} recommendations | ${result.totalSavings.toFixed(2)}/mo savings
                                            </p>
                                            <p className="text-xs text-green-600 mt-1">Saved to: {result.filepath}</p>
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => setShowPreview(!showPreview)}
                                                className="flex items-center gap-1 px-3 py-1.5 bg-green-100 hover:bg-green-200 text-green-800 rounded-lg text-sm font-medium transition"
                                            >
                                                {showPreview ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                {showPreview ? 'Hide' : 'Show'}
                                            </button>
                                            <button
                                                onClick={downloadReport}
                                                className="flex items-center gap-1 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition"
                                            >
                                                <Download className="w-4 h-4" />
                                                Download
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                {/* Report Preview */}
                                {showPreview && (
                                    <div className="border border-gray-200 rounded-lg overflow-hidden">
                                        <div className="bg-gray-100 px-4 py-2 border-b border-gray-200 flex items-center justify-between">
                                            <span className="text-sm font-medium text-gray-700">Preview: {result.filename}</span>
                                            <span className="text-xs text-gray-500">{format.toUpperCase()}</span>
                                        </div>
                                        {format === 'html' ? (
                                            <iframe
                                                srcDoc={result.content}
                                                className="w-full h-96 bg-white"
                                                title="Report Preview"
                                            />
                                        ) : (
                                            <pre className="p-4 text-sm text-gray-800 bg-gray-50 overflow-auto max-h-96 font-mono">
                                                {result.content}
                                            </pre>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                                <p className="font-medium text-red-800">Failed</p>
                                <p className="text-sm text-red-700 mt-1">{error}</p>
                            </div>
                        )}
                    </div>

                    <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t border-gray-100 rounded-b-2xl">
                        <button
                            onClick={generateReport}
                            disabled={isGenerating}
                            className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isGenerating ? 'bg-gray-300 text-gray-500' : 'bg-purple-600 text-white hover:bg-purple-700'
                                }`}
                        >
                            {isGenerating ? (
                                <>
                                    <RefreshCw className="w-5 h-5 animate-spin" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <FileText className="w-5 h-5" />
                                    {result ? 'Regenerate Report' : 'Generate Report'}
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

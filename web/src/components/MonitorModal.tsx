'use client';

import { useState } from 'react';
import { X, Play, RefreshCw, Clock, Bell, AlertTriangle } from 'lucide-react';

interface MonitorModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function MonitorModal({ isOpen, onClose }: MonitorModalProps) {
    const [interval, setInterval] = useState(60);
    const [threshold, setThreshold] = useState(100);
    const [slackWebhook, setSlackWebhook] = useState('');
    const [runOnce, setRunOnce] = useState(true);
    const [isRunning, setIsRunning] = useState(false);
    const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'error'>('idle');
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    const startMonitor = async () => {
        setIsRunning(true);
        setError(null);
        setStatus('running');

        try {
            const response = await fetch('http://localhost:8000/api/monitor', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    interval,
                    threshold,
                    slackWebhook: slackWebhook || undefined,
                    runOnce,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to start monitoring');
            }

            const data = await response.json();
            setResult(data);
            setStatus('completed');
        } catch (err: any) {
            setError(err.message || 'Failed to start monitoring');
            setStatus('error');
        } finally {
            setIsRunning(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 overflow-y-auto">
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

            <div className="relative min-h-screen flex items-center justify-center p-4">
                <div className="relative bg-white rounded-2xl shadow-2xl max-w-lg w-full">
                    <div className="sticky top-0 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between rounded-t-2xl">
                        <div className="flex items-center gap-3">
                            <Clock className="w-5 h-5 text-orange-600" />
                            <h2 className="text-xl font-bold text-gray-900">Cost Monitor</h2>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
                            <X className="w-5 h-5 text-gray-600" />
                        </button>
                    </div>

                    <div className="p-6 space-y-6">
                        <p className="text-gray-600 text-sm">
                            Monitor your AWS costs and get alerts when savings opportunities exceed your threshold.
                        </p>

                        {/* Run Mode */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">Run Mode</label>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => setRunOnce(true)}
                                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${runOnce ? 'bg-orange-600 text-white' : 'bg-gray-100 text-gray-700'
                                        }`}
                                >
                                    Run Once
                                </button>
                                <button
                                    onClick={() => setRunOnce(false)}
                                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition ${!runOnce ? 'bg-orange-600 text-white' : 'bg-gray-100 text-gray-700'
                                        }`}
                                >
                                    Continuous
                                </button>
                            </div>
                        </div>

                        {/* Interval */}
                        {!runOnce && (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Check Interval (minutes)
                                </label>
                                <input
                                    type="number"
                                    value={interval}
                                    onChange={(e) => setInterval(parseInt(e.target.value) || 60)}
                                    min={1}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                />
                            </div>
                        )}

                        {/* Threshold */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Savings Alert Threshold ($)
                            </label>
                            <input
                                type="number"
                                value={threshold}
                                onChange={(e) => setThreshold(parseFloat(e.target.value) || 100)}
                                min={0}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                Alert when monthly savings opportunities exceed this amount
                            </p>
                        </div>

                        {/* Slack Webhook */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                <Bell className="inline w-4 h-4 mr-1" />
                                Slack Webhook URL (optional)
                            </label>
                            <input
                                type="url"
                                value={slackWebhook}
                                onChange={(e) => setSlackWebhook(e.target.value)}
                                placeholder="https://hooks.slack.com/services/..."
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-500"
                            />
                        </div>

                        {/* Result */}
                        {status === 'completed' && result && (
                            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                                <p className="font-medium text-green-800">✅ Monitor Check Complete</p>
                                <div className="mt-2 text-sm text-green-700">
                                    <p>Instances Checked: {result.instancesChecked || 0}</p>
                                    <p>Total Potential Savings: ${result.totalSavings?.toFixed(2) || '0.00'}/mo</p>
                                </div>
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
                                <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0" />
                                <div>
                                    <p className="font-medium text-red-800">Error</p>
                                    <p className="text-sm text-red-700">{error}</p>
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t border-gray-100 rounded-b-2xl">
                        <button
                            onClick={startMonitor}
                            disabled={isRunning}
                            className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isRunning ? 'bg-gray-300 text-gray-500' : 'bg-orange-600 text-white hover:bg-orange-700'
                                }`}
                        >
                            {isRunning ? (
                                <>
                                    <RefreshCw className="w-5 h-5 animate-spin" />
                                    Checking...
                                </>
                            ) : (
                                <>
                                    <Play className="w-5 h-5" />
                                    {runOnce ? 'Run Check' : 'Start Monitor'}
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

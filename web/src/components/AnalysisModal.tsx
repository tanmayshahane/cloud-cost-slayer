'use client';

import { useState, useEffect } from 'react';
import {
    X,
    Play,
    Settings,
    RefreshCw,
    Key,
    Globe,
    Eye,
    EyeOff
} from 'lucide-react';

interface AnalysisModalProps {
    isOpen: boolean;
    onClose: () => void;
    onComplete: () => void;
}

export default function AnalysisModal({ isOpen, onClose, onComplete }: AnalysisModalProps) {
    // AWS Credentials
    const [awsAccessKey, setAwsAccessKey] = useState('');
    const [awsSecretKey, setAwsSecretKey] = useState('');
    const [awsProfile, setAwsProfile] = useState('default');
    const [useProfile, setUseProfile] = useState(true);
    const [showSecretKey, setShowSecretKey] = useState(false);

    // Analysis Configuration
    const [selectedRegions, setSelectedRegions] = useState<string[]>(['us-east-1']);
    const [lookbackDays, setLookbackDays] = useState(30);
    const [minSavings, setMinSavings] = useState(0);
    const [includeProduction, setIncludeProduction] = useState(false);
    const [includeRds, setIncludeRds] = useState(true);

    // State
    const [isRunning, setIsRunning] = useState(false);
    const [progress, setProgress] = useState(0);
    const [progressMessage, setProgressMessage] = useState('');
    const [error, setError] = useState<string | null>(null);

    const availableRegions = [
        { code: 'us-east-1', name: 'US East (N. Virginia)' },
        { code: 'us-west-2', name: 'US West (Oregon)' },
        { code: 'eu-west-1', name: 'EU (Ireland)' },
        { code: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
        { code: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
    ];

    const toggleRegion = (region: string) => {
        setSelectedRegions(prev =>
            prev.includes(region)
                ? prev.filter(r => r !== region)
                : [...prev, region]
        );
    };

    const startAnalysis = async () => {
        setIsRunning(true);
        setProgress(0);
        setError(null);

        try {
            const config = {
                ...(useProfile
                    ? { profile: awsProfile }
                    : { accessKey: awsAccessKey, secretKey: awsSecretKey }
                ),
                regions: selectedRegions,
                lookbackDays,
                minSavings,
                includeProduction,
                includeRds,
            };

            const response = await fetch('http://localhost:8000/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });

            if (!response.ok) {
                throw new Error('Failed to start analysis');
            }

            const data = await response.json();
            const analysisId = data.id;

            // Poll for status
            const pollStatus = async () => {
                const statusRes = await fetch(`http://localhost:8000/api/analyze/${analysisId}`);
                const status = await statusRes.json();

                setProgress(status.progress);

                if (status.progress < 30) {
                    setProgressMessage('Collecting EC2 instances...');
                } else if (status.progress < 50) {
                    setProgressMessage('Collecting RDS databases...');
                } else if (status.progress < 70) {
                    setProgressMessage('Fetching CloudWatch metrics...');
                } else if (status.progress < 90) {
                    setProgressMessage('Analyzing usage patterns...');
                } else {
                    setProgressMessage('Generating recommendations...');
                }

                if (status.status === 'completed') {
                    setIsRunning(false);
                    onComplete();
                    onClose();
                } else if (status.status === 'failed') {
                    setError(status.error || 'Analysis failed');
                    setIsRunning(false);
                } else {
                    setTimeout(pollStatus, 1000);
                }
            };

            pollStatus();

        } catch (err: any) {
            setError(err.message || 'Failed to run analysis');
            setIsRunning(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 overflow-y-auto">
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/50 backdrop-blur-sm"
                onClick={() => !isRunning && onClose()}
            />

            {/* Modal */}
            <div className="relative min-h-screen flex items-center justify-center p-4">
                <div className="relative bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
                    {/* Header */}
                    <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
                        <h2 className="text-xl font-bold text-gray-900">Run Cost Analysis</h2>
                        {!isRunning && (
                            <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg text-gray-700">
                                <X className="w-5 h-5 text-gray-600" />
                            </button>
                        )}
                    </div>

                    <div className="p-6 space-y-6">
                        {/* AWS Credentials */}
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <Key className="w-5 h-5 text-gray-600" />
                                <h3 className="font-semibold text-gray-900">AWS Credentials</h3>
                            </div>

                            <div className="flex gap-4 mb-4">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={useProfile}
                                        onChange={() => setUseProfile(true)}
                                        className="w-4 h-4 text-blue-600"
                                        disabled={isRunning}
                                    />
                                    <span className="text-sm text-gray-800">Use AWS Profile</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={!useProfile}
                                        onChange={() => setUseProfile(false)}
                                        className="w-4 h-4 text-blue-600"
                                        disabled={isRunning}
                                    />
                                    <span className="text-sm text-gray-800">Use Access Keys</span>
                                </label>
                            </div>

                            {useProfile ? (
                                <input
                                    type="text"
                                    value={awsProfile}
                                    onChange={(e) => setAwsProfile(e.target.value)}
                                    placeholder="default"
                                    disabled={isRunning}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:opacity-50 text-gray-900 placeholder:text-gray-500"
                                />
                            ) : (
                                <div className="space-y-3">
                                    <input
                                        type="text"
                                        value={awsAccessKey}
                                        onChange={(e) => setAwsAccessKey(e.target.value)}
                                        placeholder="AWS Access Key ID"
                                        disabled={isRunning}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm disabled:opacity-50 text-gray-900 placeholder:text-gray-500"
                                    />
                                    <div className="relative">
                                        <input
                                            type={showSecretKey ? 'text' : 'password'}
                                            value={awsSecretKey}
                                            onChange={(e) => setAwsSecretKey(e.target.value)}
                                            placeholder="AWS Secret Access Key"
                                            disabled={isRunning}
                                            className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm pr-10 disabled:opacity-50 text-gray-900 placeholder:text-gray-500"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowSecretKey(!showSecretKey)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"
                                        >
                                            {showSecretKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Regions */}
                        <div>
                            <div className="flex items-center gap-2 mb-3">
                                <Globe className="w-5 h-5 text-gray-600" />
                                <h3 className="font-semibold text-gray-900">Regions</h3>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {availableRegions.map(region => (
                                    <button
                                        key={region.code}
                                        onClick={() => !isRunning && toggleRegion(region.code)}
                                        disabled={isRunning}
                                        className={`px-3 py-1.5 rounded-lg text-sm transition disabled:opacity-50 ${selectedRegions.includes(region.code)
                                            ? 'bg-blue-600 text-white'
                                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                            }`}
                                    >
                                        {region.code}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Options */}
                        <div>
                            <div className="flex items-center gap-2 mb-3">
                                <Settings className="w-5 h-5 text-gray-600" />
                                <h3 className="font-semibold text-gray-900">Options</h3>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Lookback Days</label>
                                    <input
                                        type="number"
                                        value={lookbackDays}
                                        onChange={(e) => setLookbackDays(parseInt(e.target.value) || 30)}
                                        min={1}
                                        max={90}
                                        disabled={isRunning}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:opacity-50 text-gray-900"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Min Savings $</label>
                                    <input
                                        type="number"
                                        value={minSavings}
                                        onChange={(e) => setMinSavings(parseFloat(e.target.value) || 0)}
                                        min={0}
                                        disabled={isRunning}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:opacity-50 text-gray-900"
                                    />
                                </div>
                            </div>
                            <div className="mt-4 space-y-2">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={includeProduction}
                                        onChange={() => setIncludeProduction(!includeProduction)}
                                        disabled={isRunning}
                                        className="w-4 h-4 text-blue-600 rounded"
                                    />
                                    <span className="text-sm text-gray-800">Include production instances</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={includeRds}
                                        onChange={() => setIncludeRds(!includeRds)}
                                        disabled={isRunning}
                                        className="w-4 h-4 text-blue-600 rounded"
                                    />
                                    <span className="text-sm text-gray-800">Include RDS databases</span>
                                </label>
                            </div>
                        </div>

                        {/* Progress */}
                        {isRunning && (
                            <div className="bg-blue-50 rounded-lg p-4">
                                <div className="flex justify-between text-sm mb-2">
                                    <span className="text-blue-700">{progressMessage}</span>
                                    <span className="text-blue-700">{progress}%</span>
                                </div>
                                <div className="w-full bg-blue-200 rounded-full h-2">
                                    <div
                                        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                                <p className="font-medium">Analysis Failed</p>
                                <p className="text-sm mt-1">{error}</p>
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t border-gray-100">
                        <button
                            onClick={startAnalysis}
                            disabled={isRunning || selectedRegions.length === 0 || (!useProfile && (!awsAccessKey || !awsSecretKey))}
                            className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isRunning || selectedRegions.length === 0 || (!useProfile && (!awsAccessKey || !awsSecretKey))
                                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                : 'bg-blue-600 text-white hover:bg-blue-700'
                                }`}
                        >
                            {isRunning ? (
                                <>
                                    <RefreshCw className="w-5 h-5 animate-spin" />
                                    Analyzing...
                                </>
                            ) : (
                                <>
                                    <Play className="w-5 h-5" />
                                    Start Analysis
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

'use client';

import { useState, useEffect } from 'react';
import {
    Play,
    Settings,
    RefreshCw,
    CheckCircle,
    Clock,
    AlertCircle,
    Key,
    Globe,
    Filter,
    DollarSign,
    Database,
    Server,
    Eye,
    EyeOff
} from 'lucide-react';

interface AnalysisRun {
    id: string;
    status: 'running' | 'completed' | 'failed';
    progress: number;
    regions: string[];
    instancesAnalyzed: number;
    startedAt: string;
    error?: string;
}

interface AnalysisResult {
    ec2Instances: number;
    rdsInstances: number;
    totalCurrentCost: number;
    totalSavings: number;
    recommendations: any[];
}

export default function AnalyzePage() {
    // AWS Credentials
    const [awsAccessKey, setAwsAccessKey] = useState('');
    const [awsSecretKey, setAwsSecretKey] = useState('');
    const [awsProfile, setAwsProfile] = useState('default');
    const [useProfile, setUseProfile] = useState(true);
    const [showSecretKey, setShowSecretKey] = useState(false);

    // Analysis Configuration (matching CLI flags)
    const [selectedRegions, setSelectedRegions] = useState<string[]>(['us-east-1']);
    const [lookbackDays, setLookbackDays] = useState(30);
    const [minSavings, setMinSavings] = useState(0);
    const [includeProduction, setIncludeProduction] = useState(false);
    const [includeRds, setIncludeRds] = useState(true);
    const [confidenceLevel, setConfidenceLevel] = useState('all');

    // Exclude tags
    const [excludeTagKey, setExcludeTagKey] = useState('Environment');
    const [excludeTagValue, setExcludeTagValue] = useState('production');

    // State
    const [isRunning, setIsRunning] = useState(false);
    const [progress, setProgress] = useState(0);
    const [progressMessage, setProgressMessage] = useState('');
    const [result, setResult] = useState<AnalysisResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'config' | 'results'>('config');

    const [recentRuns, setRecentRuns] = useState<AnalysisRun[]>([]);

    const availableRegions = [
        { code: 'us-east-1', name: 'US East (N. Virginia)' },
        { code: 'us-west-2', name: 'US West (Oregon)' },
        { code: 'eu-west-1', name: 'EU (Ireland)' },
        { code: 'eu-central-1', name: 'EU (Frankfurt)' },
        { code: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
        { code: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
        { code: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)' },
        { code: 'sa-east-1', name: 'South America (São Paulo)' },
    ];

    const startAnalysis = async () => {
        setIsRunning(true);
        setProgress(0);
        setError(null);
        setResult(null);
        setActiveTab('config');

        try {
            const config = {
                // Credentials
                ...(useProfile
                    ? { profile: awsProfile }
                    : { accessKey: awsAccessKey, secretKey: awsSecretKey }
                ),
                // Analysis options
                regions: selectedRegions,
                lookbackDays,
                minSavings,
                includeProduction,
                includeRds,
                confidenceLevel: confidenceLevel === 'all' ? undefined : confidenceLevel,
                excludeTags: excludeTagKey && excludeTagValue
                    ? { [excludeTagKey]: excludeTagValue }
                    : undefined,
            };

            // Call API
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
                } else if (status.progress < 60) {
                    setProgressMessage('Fetching CloudWatch metrics...');
                } else if (status.progress < 90) {
                    setProgressMessage('Analyzing usage patterns...');
                } else {
                    setProgressMessage('Generating recommendations...');
                }

                if (status.status === 'completed') {
                    setResult({
                        ec2Instances: status.instancesAnalyzed,
                        rdsInstances: 0,
                        totalCurrentCost: 0,
                        totalSavings: status.totalSavings,
                        recommendations: [],
                    });
                    setActiveTab('results');
                    setIsRunning(false);

                    // Add to recent runs
                    setRecentRuns(prev => [{
                        id: analysisId,
                        status: 'completed',
                        progress: 100,
                        regions: selectedRegions,
                        instancesAnalyzed: status.instancesAnalyzed,
                        startedAt: new Date().toISOString(),
                    }, ...prev.slice(0, 4)]);

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

    const toggleRegion = (region: string) => {
        setSelectedRegions(prev =>
            prev.includes(region)
                ? prev.filter(r => r !== region)
                : [...prev, region]
        );
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed': return <CheckCircle className="w-5 h-5 text-green-500" />;
            case 'running': return <RefreshCw className="w-5 h-5 text-blue-500 animate-spin" />;
            case 'failed': return <AlertCircle className="w-5 h-5 text-red-500" />;
            default: return <Clock className="w-5 h-5 text-gray-400" />;
        }
    };

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <header className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white">
                <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold">Run Analysis</h1>
                            <p className="mt-1 text-blue-100">Scan your AWS infrastructure for optimization opportunities</p>
                        </div>
                        <a href="/" className="text-white/80 hover:text-white text-sm">← Back to Dashboard</a>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Configuration Panel */}
                    <div className="lg:col-span-2 space-y-6">

                        {/* AWS Credentials */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                            <div className="flex items-center gap-3 mb-6">
                                <Key className="w-5 h-5 text-gray-400" />
                                <h2 className="text-lg font-semibold">AWS Credentials</h2>
                            </div>

                            {/* Toggle: Profile vs Keys */}
                            <div className="flex gap-4 mb-4">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={useProfile}
                                        onChange={() => setUseProfile(true)}
                                        className="w-4 h-4 text-blue-600"
                                    />
                                    <span className="text-sm">Use AWS Profile</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        checked={!useProfile}
                                        onChange={() => setUseProfile(false)}
                                        className="w-4 h-4 text-blue-600"
                                    />
                                    <span className="text-sm">Use Access Keys</span>
                                </label>
                            </div>

                            {useProfile ? (
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        AWS Profile Name
                                    </label>
                                    <input
                                        type="text"
                                        value={awsProfile}
                                        onChange={(e) => setAwsProfile(e.target.value)}
                                        placeholder="default"
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    />
                                    <p className="mt-1 text-xs text-gray-500">
                                        Uses credentials from ~/.aws/credentials
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            AWS Access Key ID
                                        </label>
                                        <input
                                            type="text"
                                            value={awsAccessKey}
                                            onChange={(e) => setAwsAccessKey(e.target.value)}
                                            placeholder="AKIAIOSFODNN7EXAMPLE"
                                            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            AWS Secret Access Key
                                        </label>
                                        <div className="relative">
                                            <input
                                                type={showSecretKey ? 'text' : 'password'}
                                                value={awsSecretKey}
                                                onChange={(e) => setAwsSecretKey(e.target.value)}
                                                placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                                                className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm pr-10"
                                            />
                                            <button
                                                type="button"
                                                onClick={() => setShowSecretKey(!showSecretKey)}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                                            >
                                                {showSecretKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                            </button>
                                        </div>
                                        <p className="mt-1 text-xs text-yellow-600">
                                            ⚠️ Keys are sent to the local API server only. Never share publicly.
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Region Selection */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                            <div className="flex items-center gap-3 mb-4">
                                <Globe className="w-5 h-5 text-gray-400" />
                                <h2 className="text-lg font-semibold">Regions</h2>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {availableRegions.map(region => (
                                    <button
                                        key={region.code}
                                        onClick={() => toggleRegion(region.code)}
                                        className={`px-3 py-1.5 rounded-lg text-sm transition ${selectedRegions.includes(region.code)
                                                ? 'bg-blue-600 text-white'
                                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                            }`}
                                        title={region.name}
                                    >
                                        {region.code}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Analysis Options */}
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                            <div className="flex items-center gap-3 mb-6">
                                <Settings className="w-5 h-5 text-gray-400" />
                                <h2 className="text-lg font-semibold">Analysis Options</h2>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* Lookback Days */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Lookback Days (--days)
                                    </label>
                                    <input
                                        type="number"
                                        value={lookbackDays}
                                        onChange={(e) => setLookbackDays(parseInt(e.target.value) || 30)}
                                        min={1}
                                        max={90}
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                                    />
                                    <p className="mt-1 text-xs text-gray-500">Days of CloudWatch metrics to analyze</p>
                                </div>

                                {/* Min Savings */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Min Savings $ (--min-savings)
                                    </label>
                                    <input
                                        type="number"
                                        value={minSavings}
                                        onChange={(e) => setMinSavings(parseFloat(e.target.value) || 0)}
                                        min={0}
                                        step={5}
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                                    />
                                    <p className="mt-1 text-xs text-gray-500">Only show recommendations above this threshold</p>
                                </div>

                                {/* Confidence Level */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Confidence Level
                                    </label>
                                    <select
                                        value={confidenceLevel}
                                        onChange={(e) => setConfidenceLevel(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                                    >
                                        <option value="all">All Confidence Levels</option>
                                        <option value="high">High Only</option>
                                        <option value="medium">Medium & Above</option>
                                    </select>
                                </div>

                                {/* Exclude Tag */}
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Exclude Tag (--exclude-tag)
                                    </label>
                                    <div className="flex gap-2">
                                        <input
                                            type="text"
                                            value={excludeTagKey}
                                            onChange={(e) => setExcludeTagKey(e.target.value)}
                                            placeholder="Key"
                                            className="w-1/2 px-3 py-2 border border-gray-200 rounded-lg text-sm"
                                        />
                                        <input
                                            type="text"
                                            value={excludeTagValue}
                                            onChange={(e) => setExcludeTagValue(e.target.value)}
                                            placeholder="Value"
                                            className="w-1/2 px-3 py-2 border border-gray-200 rounded-lg text-sm"
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* Checkboxes */}
                            <div className="mt-6 space-y-3">
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={includeProduction}
                                        onChange={() => setIncludeProduction(!includeProduction)}
                                        className="w-4 h-4 text-blue-600 rounded"
                                    />
                                    <span className="text-sm text-gray-700">Include production instances (--include-production)</span>
                                </label>

                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={includeRds}
                                        onChange={() => setIncludeRds(!includeRds)}
                                        className="w-4 h-4 text-blue-600 rounded"
                                    />
                                    <span className="text-sm text-gray-700">Include RDS databases</span>
                                </label>
                            </div>
                        </div>

                        {/* Progress */}
                        {isRunning && (
                            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                                <div className="flex justify-between text-sm mb-2">
                                    <span className="text-gray-600">{progressMessage}</span>
                                    <span className="text-gray-600">{progress}%</span>
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-2">
                                    <div
                                        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                                <p className="font-medium">Analysis Failed</p>
                                <p className="text-sm mt-1">{error}</p>
                            </div>
                        )}

                        {/* Results Summary */}
                        {result && (
                            <div className="bg-green-50 border border-green-200 rounded-xl p-6">
                                <h3 className="font-semibold text-green-800 mb-4">✅ Analysis Complete</h3>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="text-center">
                                        <p className="text-2xl font-bold text-green-700">{result.ec2Instances}</p>
                                        <p className="text-sm text-green-600">EC2 Instances</p>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-2xl font-bold text-green-700">{result.rdsInstances}</p>
                                        <p className="text-sm text-green-600">RDS Databases</p>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-2xl font-bold text-green-700">${result.totalSavings.toFixed(2)}</p>
                                        <p className="text-sm text-green-600">Monthly Savings</p>
                                    </div>
                                    <div className="text-center">
                                        <p className="text-2xl font-bold text-green-700">${(result.totalSavings * 12).toFixed(0)}</p>
                                        <p className="text-sm text-green-600">Annual Savings</p>
                                    </div>
                                </div>
                                <div className="mt-4 text-center">
                                    <a
                                        href="/recommendations"
                                        className="inline-block px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition"
                                    >
                                        View Recommendations →
                                    </a>
                                </div>
                            </div>
                        )}

                        {/* Start Button */}
                        <button
                            onClick={startAnalysis}
                            disabled={isRunning || selectedRegions.length === 0 || (!useProfile && (!awsAccessKey || !awsSecretKey))}
                            className={`w-full flex items-center justify-center gap-2 py-4 rounded-xl font-medium text-lg transition ${isRunning || selectedRegions.length === 0 || (!useProfile && (!awsAccessKey || !awsSecretKey))
                                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                    : 'bg-blue-600 text-white hover:bg-blue-700'
                                }`}
                        >
                            {isRunning ? (
                                <>
                                    <RefreshCw className="w-5 h-5 animate-spin" />
                                    Running Analysis...
                                </>
                            ) : (
                                <>
                                    <Play className="w-5 h-5" />
                                    Start Analysis
                                </>
                            )}
                        </button>
                    </div>

                    {/* Recent Runs */}
                    <div>
                        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                            <h2 className="text-lg font-semibold mb-4">Recent Analyses</h2>

                            {recentRuns.length === 0 ? (
                                <p className="text-gray-500 text-sm">No recent analyses</p>
                            ) : (
                                <div className="space-y-4">
                                    {recentRuns.map(run => (
                                        <div key={run.id} className="p-4 bg-gray-50 rounded-lg">
                                            <div className="flex items-center gap-3 mb-2">
                                                {getStatusIcon(run.status)}
                                                <span className="font-medium capitalize">{run.status}</span>
                                            </div>
                                            <div className="text-sm text-gray-500 space-y-1">
                                                <p>{run.regions.join(', ')}</p>
                                                <p>{run.instancesAnalyzed} instances analyzed</p>
                                                <p>{new Date(run.startedAt).toLocaleString()}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* CLI Equivalent */}
                        <div className="mt-6 bg-gray-900 rounded-xl p-4">
                            <h3 className="text-gray-400 text-sm mb-2">CLI Equivalent:</h3>
                            <code className="text-green-400 text-xs break-all">
                                cloud-cost-slayer analyze{' '}
                                --region {selectedRegions.join(',')}
                                {' '}--days {lookbackDays}
                                {minSavings > 0 ? ` --min-savings ${minSavings}` : ''}
                                {includeProduction ? ' --include-production' : ''}
                            </code>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}

'use client';

import { useState, useEffect } from 'react';
import { X, Settings, Save, RefreshCw, Check, AlertTriangle, Eye, EyeOff } from 'lucide-react';

interface ConfigModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function ConfigModal({ isOpen, onClose }: ConfigModalProps) {
    const [activeTab, setActiveTab] = useState<'credentials' | 'defaults' | 'test'>('credentials');

    // Credentials
    const [awsProfile, setAwsProfile] = useState('default');
    const [awsAccessKey, setAwsAccessKey] = useState('');
    const [awsSecretKey, setAwsSecretKey] = useState('');
    const [showSecretKey, setShowSecretKey] = useState(false);

    // Defaults
    const [defaultRegion, setDefaultRegion] = useState('us-east-1');
    const [defaultLookbackDays, setDefaultLookbackDays] = useState(30);
    const [defaultMinSavings, setDefaultMinSavings] = useState(10);
    const [excludeProduction, setExcludeProduction] = useState(true);

    // State
    const [isSaving, setIsSaving] = useState(false);
    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);

    const saveConfig = async () => {
        setIsSaving(true);
        setError(null);
        setSaved(false);

        try {
            const response = await fetch('http://localhost:8000/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    awsProfile,
                    awsAccessKey: awsAccessKey || undefined,
                    awsSecretKey: awsSecretKey || undefined,
                    defaultRegion,
                    defaultLookbackDays,
                    defaultMinSavings,
                    excludeProduction,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to save configuration');
            }

            setSaved(true);
            setTimeout(() => setSaved(false), 3000);
        } catch (err: any) {
            setError(err.message || 'Failed to save configuration');
        } finally {
            setIsSaving(false);
        }
    };

    const testCredentials = async () => {
        setIsTesting(true);
        setTestResult(null);
        setError(null);

        try {
            const response = await fetch('http://localhost:8000/api/config/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    profile: awsProfile,
                    accessKey: awsAccessKey || undefined,
                    secretKey: awsSecretKey || undefined,
                }),
            });

            const data = await response.json();
            setTestResult(data);
        } catch (err: any) {
            setError(err.message || 'Failed to test credentials');
        } finally {
            setIsTesting(false);
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
                            <Settings className="w-5 h-5 text-gray-600" />
                            <h2 className="text-xl font-bold text-gray-900">Configuration</h2>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
                            <X className="w-5 h-5 text-gray-600" />
                        </button>
                    </div>

                    {/* Tabs */}
                    <div className="flex border-b border-gray-200">
                        {(['credentials', 'defaults', 'test'] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`flex-1 py-3 text-sm font-medium transition ${activeTab === tab
                                    ? 'text-blue-600 border-b-2 border-blue-600'
                                    : 'text-gray-500 hover:text-gray-700'
                                    }`}
                            >
                                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                            </button>
                        ))}
                    </div>

                    <div className="p-6 space-y-6">
                        {/* Credentials Tab */}
                        {activeTab === 'credentials' && (
                            <>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        AWS Profile Name
                                    </label>
                                    <input
                                        type="text"
                                        value={awsProfile}
                                        onChange={(e) => setAwsProfile(e.target.value)}
                                        placeholder="default"
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                    />
                                    <p className="text-xs text-gray-500 mt-1">
                                        Profile from ~/.aws/credentials
                                    </p>
                                </div>

                                <div className="relative">
                                    <div className="absolute inset-0 flex items-center">
                                        <div className="w-full border-t border-gray-200" />
                                    </div>
                                    <div className="relative flex justify-center">
                                        <span className="px-2 bg-white text-sm text-gray-500">or use access keys</span>
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        AWS Access Key ID
                                    </label>
                                    <input
                                        type="text"
                                        value={awsAccessKey}
                                        onChange={(e) => setAwsAccessKey(e.target.value)}
                                        placeholder="AKIAIOSFODNN7EXAMPLE"
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm text-gray-900 placeholder:text-gray-500"
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
                                            placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLE"
                                            className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm text-gray-900 placeholder:text-gray-500 pr-10"
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
                            </>
                        )}

                        {/* Defaults Tab */}
                        {activeTab === 'defaults' && (
                            <>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Default Region
                                    </label>
                                    <select
                                        value={defaultRegion}
                                        onChange={(e) => setDefaultRegion(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                    >
                                        <option value="us-east-1">us-east-1 (N. Virginia)</option>
                                        <option value="us-west-2">us-west-2 (Oregon)</option>
                                        <option value="eu-west-1">eu-west-1 (Ireland)</option>
                                        <option value="ap-south-1">ap-south-1 (Mumbai)</option>
                                        <option value="ap-southeast-1">ap-southeast-1 (Singapore)</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Default Lookback Days
                                    </label>
                                    <input
                                        type="number"
                                        value={defaultLookbackDays}
                                        onChange={(e) => setDefaultLookbackDays(parseInt(e.target.value) || 30)}
                                        min={1}
                                        max={90}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Default Minimum Savings ($)
                                    </label>
                                    <input
                                        type="number"
                                        value={defaultMinSavings}
                                        onChange={(e) => setDefaultMinSavings(parseFloat(e.target.value) || 0)}
                                        min={0}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                    />
                                </div>

                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={excludeProduction}
                                        onChange={() => setExcludeProduction(!excludeProduction)}
                                        className="w-4 h-4 text-blue-600 rounded"
                                    />
                                    <span className="text-sm">Exclude production instances by default</span>
                                </label>
                            </>
                        )}

                        {/* Test Tab */}
                        {activeTab === 'test' && (
                            <>
                                <p className="text-gray-600 text-sm">
                                    Test your AWS credentials to ensure they have the required permissions.
                                </p>

                                <button
                                    onClick={testCredentials}
                                    disabled={isTesting}
                                    className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isTesting ? 'bg-gray-300 text-gray-500' : 'bg-blue-600 text-white hover:bg-blue-700'
                                        }`}
                                >
                                    {isTesting ? (
                                        <>
                                            <RefreshCw className="w-5 h-5 animate-spin" />
                                            Testing...
                                        </>
                                    ) : (
                                        'Test Credentials'
                                    )}
                                </button>

                                {testResult && (
                                    <div className={`p-4 rounded-lg border ${testResult.success
                                        ? 'bg-green-50 border-green-200'
                                        : 'bg-red-50 border-red-200'
                                        }`}>
                                        <p className={`font-medium flex items-center gap-2 ${testResult.success ? 'text-green-800' : 'text-red-800'
                                            }`}>
                                            {testResult.success ? (
                                                <><Check className="w-5 h-5" /> Credentials Valid</>
                                            ) : (
                                                <><AlertTriangle className="w-5 h-5" /> Credentials Invalid</>
                                            )}
                                        </p>
                                        {testResult.accountId && (
                                            <p className="text-sm mt-1 text-green-700">
                                                Account ID: {testResult.accountId}
                                            </p>
                                        )}
                                        {testResult.error && (
                                            <p className="text-sm mt-1 text-red-700">{testResult.error}</p>
                                        )}
                                    </div>
                                )}
                            </>
                        )}

                        {/* Success */}
                        {saved && (
                            <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-green-700 flex items-center gap-2">
                                <Check className="w-5 h-5" />
                                Configuration saved successfully
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                                <p className="font-medium">Error</p>
                                <p className="text-sm">{error}</p>
                            </div>
                        )}
                    </div>

                    {activeTab !== 'test' && (
                        <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t border-gray-100 rounded-b-2xl">
                            <button
                                onClick={saveConfig}
                                disabled={isSaving}
                                className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isSaving ? 'bg-gray-300 text-gray-500' : 'bg-blue-600 text-white hover:bg-blue-700'
                                    }`}
                            >
                                {isSaving ? (
                                    <>
                                        <RefreshCw className="w-5 h-5 animate-spin" />
                                        Saving...
                                    </>
                                ) : (
                                    <>
                                        <Save className="w-5 h-5" />
                                        Save Configuration
                                    </>
                                )}
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

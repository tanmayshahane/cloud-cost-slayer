'use client';

import { useState } from 'react';
import { X, Clock, Save, RefreshCw, AlertTriangle } from 'lucide-react';

interface ScheduleModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function ScheduleModal({ isOpen, onClose }: ScheduleModalProps) {
    const [instanceId, setInstanceId] = useState('');
    const [startTime, setStartTime] = useState('08:00');
    const [stopTime, setStopTime] = useState('18:00');
    const [timezone, setTimezone] = useState('UTC');
    const [weekdaysOnly, setWeekdaysOnly] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    const timezones = [
        'UTC',
        'America/New_York',
        'America/Los_Angeles',
        'Europe/London',
        'Europe/Paris',
        'Asia/Tokyo',
        'Asia/Kolkata',
        'Asia/Singapore',
    ];

    const saveSchedule = async () => {
        if (!instanceId) {
            setError('Please enter an instance ID');
            return;
        }

        setIsSaving(true);
        setError(null);
        setResult(null);

        try {
            const response = await fetch('http://localhost:8000/api/schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    instanceId,
                    startTime,
                    stopTime,
                    timezone,
                    weekdaysOnly,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to save schedule');
            }

            const data = await response.json();
            setResult(data);
        } catch (err: any) {
            setError(err.message || 'Failed to save schedule');
        } finally {
            setIsSaving(false);
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
                            <Clock className="w-5 h-5 text-purple-600" />
                            <h2 className="text-xl font-bold text-gray-900">Schedule Start/Stop</h2>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
                            <X className="w-5 h-5 text-gray-600" />
                        </button>
                    </div>

                    <div className="p-6 space-y-6">
                        <p className="text-gray-600 text-sm">
                            Configure automatic start and stop times for your instances to save costs during off-hours.
                        </p>

                        {/* Instance ID */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Instance ID
                            </label>
                            <input
                                type="text"
                                value={instanceId}
                                onChange={(e) => setInstanceId(e.target.value)}
                                placeholder="i-0123456789abcdef0"
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm text-gray-900 placeholder:text-gray-500"
                            />
                        </div>

                        {/* Times */}
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Start Time
                                </label>
                                <input
                                    type="time"
                                    value={startTime}
                                    onChange={(e) => setStartTime(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Stop Time
                                </label>
                                <input
                                    type="time"
                                    value={stopTime}
                                    onChange={(e) => setStopTime(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                                />
                            </div>
                        </div>

                        {/* Timezone */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Timezone
                            </label>
                            <select
                                value={timezone}
                                onChange={(e) => setTimezone(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-900 placeholder:text-gray-500"
                            >
                                {timezones.map(tz => (
                                    <option key={tz} value={tz}>{tz}</option>
                                ))}
                            </select>
                        </div>

                        {/* Weekdays Only */}
                        <label className="flex items-center gap-3 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={weekdaysOnly}
                                onChange={() => setWeekdaysOnly(!weekdaysOnly)}
                                className="w-4 h-4 text-purple-600 rounded"
                            />
                            <div>
                                <span className="font-medium">Weekdays Only</span>
                                <p className="text-sm text-gray-500">Skip weekends (instance stays off)</p>
                            </div>
                        </label>

                        {/* Savings Estimate */}
                        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                            <p className="text-sm text-green-800">
                                💰 <strong>Estimated Savings:</strong> Running 10 hours/day instead of 24 hours
                                saves approximately <strong>58%</strong> on compute costs.
                            </p>
                        </div>

                        {/* Result */}
                        {result && (
                            <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-green-700">
                                <p className="font-medium">✅ Schedule Saved</p>
                                <p className="text-sm mt-1">
                                    Instance will start at {startTime} and stop at {stopTime} ({timezone})
                                </p>
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
                            onClick={saveSchedule}
                            disabled={isSaving}
                            className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition ${isSaving ? 'bg-gray-300 text-gray-500' : 'bg-purple-600 text-white hover:bg-purple-700'
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
                                    Save Schedule
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

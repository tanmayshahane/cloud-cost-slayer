'use client';

import { useState, useEffect } from 'react';
import {
  DollarSign,
  TrendingDown,
  Server,
  Database,
  RefreshCw,
  PlayCircle,
  Clock,
  HardDrive,
  ChevronRight,
  FileText,
  Zap,
  Settings,
  Search,
  Cpu,
  Activity
} from 'lucide-react';
import AnalysisModal from '@/components/AnalysisModal';
import ReportModal from '@/components/ReportModal';
import MonitorModal from '@/components/MonitorModal';
import ApplyModal from '@/components/ApplyModal';
import ScheduleModal from '@/components/ScheduleModal';
import ConfigModal from '@/components/ConfigModal';
import CostSummaryHub from '@/components/CostSummaryHub';

interface Instance {
  id: string;
  name: string;
  type: string;
  region: string;
  hourlyRate: number;
  currentMonthCost: number;
  hoursThisMonth: number;
  projectedMonthCost: number;
  monthlyCost: number;
  storageCost: number;
  storageGb: number;
  cpuAvg: number;
  cpuMax: number;
  engine?: string;
  multiAz?: boolean;
  recommendation?: {
    type: string;
    message: string;
    savings: number;
    newType?: string;
  };
}

interface AnalysisResult {
  ec2Instances: Instance[];
  rdsInstances: Instance[];
  totalCurrentCost: number;
  totalPotentialSavings: number;
  lastAnalyzedAt: string;
}

export default function Dashboard() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Modal states
  const [showAnalysisModal, setShowAnalysisModal] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [showMonitorModal, setShowMonitorModal] = useState(false);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);

  useEffect(() => {
    fetchResults();
  }, []);

  const fetchResults = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/dashboard');
      if (response.ok) {
        const data = await response.json();
        if (data.hasData) {
          setResult(data);
        } else {
          setResult(null);
        }
      } else {
        setResult(null);
      }
    } catch (err) {
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  // CLI-style CPU status
  const getCpuStatus = (cpuAvg: number) => {
    if (cpuAvg < 5) return { emoji: '😴', label: 'Almost idle', desc: 'This server is barely doing anything', color: 'text-red-700', bg: 'bg-red-100' };
    if (cpuAvg < 15) return { emoji: '🌙', label: 'Light usage', desc: 'Handling minimal workload', color: 'text-amber-700', bg: 'bg-amber-100' };
    if (cpuAvg < 40) return { emoji: '⚡', label: 'Moderate', desc: 'Healthy workload', color: 'text-blue-700', bg: 'bg-blue-100' };
    return { emoji: '🔥', label: 'Heavy usage', desc: 'Working hard', color: 'text-green-700', bg: 'bg-green-100' };
  };

  // Calculate cost summary
  const getCostSummary = () => {
    if (!result) return null;

    const items: { name: string; service: string; currentCost: number; projectedCost: number; storageCost: number }[] = [];

    // Add EC2 instances
    result.ec2Instances.forEach(inst => {
      items.push({
        name: inst.name || inst.id,
        service: 'EC2',
        currentCost: inst.currentMonthCost,
        projectedCost: inst.projectedMonthCost,
        storageCost: inst.storageCost || 0,
      });
    });

    // Add RDS instances
    result.rdsInstances.forEach(inst => {
      items.push({
        name: inst.name || inst.id,
        service: 'RDS',
        currentCost: inst.currentMonthCost,
        projectedCost: inst.projectedMonthCost,
        storageCost: inst.storageCost || 0,
      });
    });

    const totalCurrentCost = items.reduce((sum, i) => sum + i.currentCost + i.storageCost, 0);
    const totalProjectedCost = items.reduce((sum, i) => sum + i.projectedCost + i.storageCost, 0);
    const totalStorageCost = items.reduce((sum, i) => sum + i.storageCost, 0);
    const totalComputeCost = items.reduce((sum, i) => sum + i.projectedCost, 0);

    return { items, totalCurrentCost, totalProjectedCost, totalStorageCost, totalComputeCost };
  };

  // Feature buttons data
  const features = [
    { id: 'analyze', icon: Search, title: 'Analyze', description: 'Scan AWS for savings', color: 'bg-blue-600', onClick: () => setShowAnalysisModal(true) },
    { id: 'apply', icon: Zap, title: 'Apply', description: 'Execute recommendations', color: 'bg-green-600', onClick: () => setShowApplyModal(true) },
    { id: 'monitor', icon: Clock, title: 'Monitor', description: 'Continuous monitoring', color: 'bg-orange-600', onClick: () => setShowMonitorModal(true) },
    { id: 'report', icon: FileText, title: 'Report', description: 'Generate reports', color: 'bg-purple-600', onClick: () => setShowReportModal(true) },
    { id: 'schedule', icon: Clock, title: 'Schedule', description: 'Auto start/stop', color: 'bg-indigo-600', onClick: () => setShowScheduleModal(true) },
    { id: 'config', icon: Settings, title: 'Config', description: 'AWS credentials', color: 'bg-gray-700', onClick: () => setShowConfigModal(true) },
  ];

  const costSummary = getCostSummary();

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-12 h-12 text-blue-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-700 font-medium">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* All Modals */}
      <AnalysisModal isOpen={showAnalysisModal} onClose={() => setShowAnalysisModal(false)} onComplete={fetchResults} />
      <ReportModal isOpen={showReportModal} onClose={() => setShowReportModal(false)} />
      <MonitorModal isOpen={showMonitorModal} onClose={() => setShowMonitorModal(false)} />
      <ApplyModal isOpen={showApplyModal} onClose={() => setShowApplyModal(false)} onComplete={fetchResults} />
      <ScheduleModal isOpen={showScheduleModal} onClose={() => setShowScheduleModal(false)} />
      <ConfigModal isOpen={showConfigModal} onClose={() => setShowConfigModal(false)} />

      <div className="min-h-screen bg-gray-100">
        {/* Header */}
        <header className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white shadow-lg">
          <div className="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center">
              <div>
                <h1 className="text-3xl font-bold">Cloud Cost Slayer</h1>
                <p className="mt-1 text-blue-200">
                  {result ? `Last Analysis: ${new Date(result.lastAnalyzedAt).toLocaleString()}` : 'Find hidden savings in your AWS infrastructure'}
                </p>
              </div>
              <div className="flex gap-3">
                <button onClick={fetchResults} className="flex items-center gap-2 bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg transition font-medium">
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </button>
                <button onClick={() => setShowConfigModal(true)} className="flex items-center gap-2 bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg transition">
                  <Settings className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
          {/* Feature Buttons Grid */}
          <div className="mb-8">
            <h2 className="text-lg font-bold text-gray-900 mb-4">Quick Actions</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {features.map(feature => (
                <button key={feature.id} onClick={feature.onClick} className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:shadow-md transition text-left group">
                  <div className={`w-10 h-10 ${feature.color} rounded-lg flex items-center justify-center mb-3 group-hover:scale-110 transition`}>
                    <feature.icon className="w-5 h-5 text-white" />
                  </div>
                  <h3 className="font-semibold text-gray-900">{feature.title}</h3>
                  <p className="text-sm text-gray-600 mt-1">{feature.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Empty State */}
          {!result && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-12 text-center">
              <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <Server className="w-10 h-10 text-blue-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-4">No Analysis Data Yet</h2>
              <p className="text-gray-700 mb-8 max-w-md mx-auto">Click &quot;Analyze&quot; above to scan your AWS infrastructure for cost optimization opportunities.</p>
              <button onClick={() => setShowAnalysisModal(true)} className="inline-flex items-center gap-2 px-8 py-4 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition text-lg font-medium shadow-lg">
                <PlayCircle className="w-6 h-6" />
                Run Your First Analysis
              </button>
              <div className="mt-8 pt-8 border-t border-gray-200">
                <p className="text-gray-600 mb-4">Or run via CLI:</p>
                <code className="bg-gray-900 text-green-400 px-4 py-2 rounded-lg text-sm font-mono">cloud-cost-slayer analyze --region us-east-1</code>
              </div>
            </div>
          )}

          {/* Results with Two-Column Layout */}
          {result && (
            <>
              {/* Summary Banner */}
              <div className="bg-gradient-to-r from-emerald-600 to-teal-600 rounded-2xl p-8 text-white mb-8 shadow-lg">
                <div className="grid md:grid-cols-3 gap-8">
                  <div>
                    <p className="text-emerald-100 text-sm font-medium mb-1">Cost So Far This Month</p>
                    <p className="text-4xl font-bold">${result.totalCurrentCost.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-emerald-100 text-sm font-medium mb-1">💰 Potential Savings</p>
                    <p className="text-4xl font-bold">${result.totalPotentialSavings.toFixed(2)}/mo</p>
                    <p className="text-emerald-200 text-sm mt-1">${(result.totalPotentialSavings * 12).toFixed(0)}/year</p>
                  </div>
                  <div>
                    <p className="text-emerald-100 text-sm font-medium mb-1">Resources Analyzed</p>
                    <p className="text-4xl font-bold">{result.ec2Instances.length + result.rdsInstances.length}</p>
                    <p className="text-emerald-200 text-sm mt-1">{result.ec2Instances.length} EC2 • {result.rdsInstances.length} RDS</p>
                  </div>
                </div>
              </div>

              {/* Instance Cards */}
              <div>
                {/* EC2 Instances */}
                {result.ec2Instances.length > 0 && (
                  <div className="mb-8">
                    <h2 className="text-xl font-bold text-gray-900 mb-2 flex items-center gap-2">
                      <Server className="w-5 h-5 text-blue-600" />
                      📊 Your EC2 Instances Analysis
                    </h2>
                    <p className="text-gray-700 mb-4">Here&apos;s what we found about your running servers:</p>

                    <div className="space-y-4">
                      {result.ec2Instances.map((instance, idx) => {
                        const cpuStatus = getCpuStatus(instance.cpuAvg);
                        const totalMonthlyCost = instance.projectedMonthCost + (instance.storageCost || 0);

                        return (
                          <div key={`ec2-${instance.id}-${idx}`} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                            <div className="mb-4">
                              <h3 className="text-lg font-bold text-gray-900">🖥️ {instance.name || instance.id}</h3>
                              <p className="text-gray-700 text-sm">ID: {instance.id} | Type: <span className="font-semibold text-gray-900">{instance.type}</span> | Region: {instance.region}</p>
                            </div>

                            <div className="mb-4">
                              <h4 className="font-semibold text-amber-800 mb-2">💰 Cost Breakdown</h4>
                              <p className="text-gray-800">This server costs <span className="text-blue-700 font-semibold">${instance.hourlyRate.toFixed(4)} per hour</span> to run.</p>
                              <p className="text-gray-800">So far this month: <span className="text-amber-700 font-bold">${instance.currentMonthCost.toFixed(2)}</span></p>
                              {(instance.storageGb > 0 || instance.storageCost > 0) && (
                                <p className="text-gray-800">Storage: {instance.storageGb || 0} GB - <span className="text-amber-700 font-bold">${(instance.storageCost || 0).toFixed(2)}/month</span></p>
                              )}
                              <p className="text-gray-900 font-bold mt-2">📊 Total Monthly Cost: <span className="text-blue-700">${totalMonthlyCost.toFixed(2)}</span></p>
                              <p className="text-gray-600 text-sm">(Server: ${instance.projectedMonthCost.toFixed(2)} + Storage: ${(instance.storageCost || 0).toFixed(2)})</p>
                            </div>

                            <div className="mb-4">
                              <h4 className="font-semibold text-amber-800 mb-2">⚡ How Hard Is It Working?</h4>
                              <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full ${cpuStatus.bg}`}>
                                <span className="text-xl">{cpuStatus.emoji}</span>
                                <span className={`font-semibold ${cpuStatus.color}`}>{instance.cpuAvg.toFixed(1)}% average CPU</span>
                              </div>
                              <p className="text-gray-700 mt-1">Peak: {instance.cpuMax.toFixed(1)}%</p>
                            </div>

                            {instance.recommendation ? (
                              <div className="bg-green-100 border border-green-300 rounded-lg p-4">
                                <h4 className="font-semibold text-green-900 mb-1">💡 Money-Saving Opportunity</h4>
                                <p className="text-green-800">{instance.recommendation.message}</p>
                                <p className="text-green-900 font-bold mt-2">Potential savings: ${instance.recommendation.savings.toFixed(2)}/month (${(instance.recommendation.savings * 12).toFixed(0)}/year)</p>
                              </div>
                            ) : (
                              <div className="bg-blue-100 border border-blue-300 rounded-lg p-4">
                                <p className="text-blue-800 font-medium">✔️ This instance appears to be appropriately sized for its workload.</p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* RDS Instances */}
                {result.rdsInstances.length > 0 && (
                  <div className="mb-8">
                    <h2 className="text-xl font-bold text-gray-900 mb-2 flex items-center gap-2">
                      <Database className="w-5 h-5 text-purple-600" />
                      🗄️ Your RDS Databases Analysis
                    </h2>
                    <p className="text-gray-700 mb-4">Here&apos;s what we found about your databases:</p>

                    <div className="space-y-4">
                      {result.rdsInstances.map((instance, idx) => {
                        const cpuStatus = getCpuStatus(instance.cpuAvg);

                        return (
                          <div key={`rds-${instance.id}-${idx}`} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                            <div className="mb-4">
                              <h3 className="text-lg font-bold text-gray-900">
                                🗄️ {instance.name || instance.id}
                                {instance.multiAz && <span className="ml-2 text-amber-700 text-sm font-normal">(Multi-AZ)</span>}
                              </h3>
                              <p className="text-gray-700 text-sm">
                                {instance.engine && <span>Engine: {instance.engine.toUpperCase()} | </span>}
                                Class: <span className="font-semibold text-gray-900">{instance.type}</span> | Region: {instance.region}
                              </p>
                            </div>

                            <div className="mb-4">
                              <h4 className="font-semibold text-amber-800 mb-2">💰 Cost Breakdown</h4>
                              <p className="text-gray-800">This database costs <span className="text-blue-700 font-semibold">${instance.hourlyRate.toFixed(4)} per hour</span> to run.</p>
                              {instance.multiAz && <p className="text-gray-600 text-sm">(Multi-AZ doubles the cost for high availability)</p>}
                              <p className="text-gray-800">So far this month: <span className="text-amber-700 font-bold">${instance.currentMonthCost.toFixed(2)}</span></p>
                              {instance.storageGb > 0 && (
                                <p className="text-gray-800">Storage: {instance.storageGb} GB - <span className="text-amber-700 font-bold">${instance.storageCost.toFixed(2)}/month</span></p>
                              )}
                              <p className="text-gray-900 font-bold mt-2">📊 Total Monthly Cost: <span className="text-blue-700">${instance.monthlyCost.toFixed(2)}</span></p>
                              {instance.storageCost > 0 && <p className="text-gray-600 text-sm">(Database: ${instance.projectedMonthCost.toFixed(2)} + Storage: ${instance.storageCost.toFixed(2)})</p>}
                            </div>

                            <div className="mb-4">
                              <h4 className="font-semibold text-amber-800 mb-2">⚡ How Hard Is It Working?</h4>
                              <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full ${cpuStatus.bg}`}>
                                <span className="text-xl">{cpuStatus.emoji}</span>
                                <span className={`font-semibold ${cpuStatus.color}`}>{instance.cpuAvg.toFixed(1)}% average CPU</span>
                              </div>
                              <p className="text-gray-700 mt-1">Peak: {instance.cpuMax.toFixed(1)}%</p>
                            </div>

                            {instance.recommendation && (
                              <div className="bg-green-100 border border-green-300 rounded-lg p-4">
                                <h4 className="font-semibold text-green-900 mb-1">💡 Money-Saving Opportunity</h4>
                                <p className="text-green-800">{instance.recommendation.message}</p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Quick Links */}
                <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                  <h2 className="text-lg font-bold text-gray-900 mb-4">Next Steps</h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <button onClick={() => setShowApplyModal(true)} className="flex items-center justify-between p-4 bg-green-100 border border-green-300 rounded-lg hover:bg-green-200 transition">
                      <div className="flex items-center gap-3">
                        <Zap className="w-5 h-5 text-green-700" />
                        <span className="font-semibold text-green-900">Apply Recommendations</span>
                      </div>
                      <ChevronRight className="w-5 h-5 text-green-700" />
                    </button>
                    <button onClick={() => setShowReportModal(true)} className="flex items-center justify-between p-4 bg-purple-100 border border-purple-300 rounded-lg hover:bg-purple-200 transition">
                      <div className="flex items-center gap-3">
                        <FileText className="w-5 h-5 text-purple-700" />
                        <span className="font-semibold text-purple-900">Generate Report</span>
                      </div>
                      <ChevronRight className="w-5 h-5 text-purple-700" />
                    </button>
                    <a href="/recommendations" className="flex items-center justify-between p-4 bg-blue-100 border border-blue-300 rounded-lg hover:bg-blue-200 transition">
                      <div className="flex items-center gap-3">
                        <TrendingDown className="w-5 h-5 text-blue-700" />
                        <span className="font-semibold text-blue-900">All Recommendations</span>
                      </div>
                      <ChevronRight className="w-5 h-5 text-blue-700" />
                    </a>
                  </div>
                </div>
              </div>

              {/* Floating Cost Summary Hub */}
              {costSummary && (
                <CostSummaryHub
                  items={costSummary.items}
                  totalPotentialSavings={result.totalPotentialSavings}
                />
              )}
            </>
          )}
        </main>
      </div>
    </>
  );
}


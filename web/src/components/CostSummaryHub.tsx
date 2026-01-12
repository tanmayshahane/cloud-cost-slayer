'use client';

import { useState } from 'react';
import { DollarSign, X, ChevronUp, ChevronDown, TrendingDown } from 'lucide-react';

interface CostItem {
    name: string;
    service: string;
    currentCost: number;
    projectedCost: number;
    storageCost: number;
}

interface CostSummaryHubProps {
    items: CostItem[];
    totalPotentialSavings?: number;
}

export default function CostSummaryHub({ items, totalPotentialSavings = 0 }: CostSummaryHubProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [isMinimized, setIsMinimized] = useState(false);

    // Calculate totals
    const totalCurrentCost = items.reduce((sum, i) => sum + i.currentCost + i.storageCost, 0);
    const totalProjectedCost = items.reduce((sum, i) => sum + i.projectedCost + i.storageCost, 0);
    const totalStorageCost = items.reduce((sum, i) => sum + i.storageCost, 0);
    const totalComputeCost = items.reduce((sum, i) => sum + i.projectedCost, 0);

    if (items.length === 0) return null;

    return (
        <>
            {/* Floating Button */}
            {!isOpen && (
                <button
                    onClick={() => setIsOpen(true)}
                    className="fixed bottom-6 right-6 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-full p-4 shadow-2xl hover:shadow-emerald-500/30 hover:scale-110 transition-all z-50 group"
                >
                    <div className="relative">
                        <DollarSign className="w-7 h-7" />
                        {/* Pulse indicator */}
                        <span className="absolute -top-1 -right-1 w-3 h-3 bg-amber-400 rounded-full animate-pulse" />
                    </div>
                    {/* Tooltip */}
                    <span className="absolute right-full mr-3 top-1/2 -translate-y-1/2 bg-gray-900 text-white text-sm px-3 py-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition whitespace-nowrap">
                        View Cost Summary
                    </span>
                </button>
            )}

            {/* Floating Panel */}
            {isOpen && (
                <div className={`fixed bottom-6 right-6 w-96 bg-white rounded-2xl shadow-2xl border border-gray-200 z-50 transition-all ${isMinimized ? 'h-16' : 'max-h-[80vh]'} overflow-hidden`}>
                    {/* Header */}
                    <div className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white p-4 flex items-center justify-between cursor-pointer" onClick={() => setIsMinimized(!isMinimized)}>
                        <div className="flex items-center gap-2">
                            <DollarSign className="w-5 h-5" />
                            <span className="font-bold">Cost Summary</span>
                            {isMinimized && (
                                <span className="ml-2 text-emerald-100 text-sm">${totalProjectedCost.toFixed(2)}/mo</span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <button onClick={(e) => { e.stopPropagation(); setIsMinimized(!isMinimized); }} className="hover:bg-white/20 p-1 rounded transition">
                                {isMinimized ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); setIsOpen(false); }} className="hover:bg-white/20 p-1 rounded transition">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                    </div>

                    {/* Content */}
                    {!isMinimized && (
                        <div className="p-4 overflow-y-auto max-h-[calc(80vh-64px)]">
                            <p className="text-gray-600 text-sm mb-4">Line-by-line breakdown of all costs</p>

                            {/* Individual Items */}
                            <div className="space-y-3 mb-4">
                                {items.map((item, idx) => (
                                    <div key={idx} className="border-b border-gray-100 pb-3">
                                        <div className="flex justify-between items-start">
                                            <div>
                                                <p className="font-medium text-gray-900 text-sm">{item.name}</p>
                                                <p className="text-xs text-gray-500">{item.service}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-amber-700 font-semibold text-sm">${(item.projectedCost + item.storageCost).toFixed(2)}</p>
                                                <p className="text-xs text-gray-500">projected</p>
                                            </div>
                                        </div>
                                        <div className="flex justify-between text-xs text-gray-600 mt-1">
                                            <span>Compute: ${item.projectedCost.toFixed(2)}</span>
                                            {item.storageCost > 0 && <span>Storage: ${item.storageCost.toFixed(2)}</span>}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Totals */}
                            <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Total Compute:</span>
                                    <span className="font-semibold text-gray-900">${totalComputeCost.toFixed(2)}</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Total Storage:</span>
                                    <span className="font-semibold text-gray-900">${totalStorageCost.toFixed(2)}</span>
                                </div>
                                <div className="border-t border-gray-200 pt-2 mt-2">
                                    <div className="flex justify-between">
                                        <span className="text-gray-700 font-medium">Current Month:</span>
                                        <span className="font-bold text-amber-700">${totalCurrentCost.toFixed(2)}</span>
                                    </div>
                                    <div className="flex justify-between mt-1">
                                        <span className="text-gray-700 font-medium">Projected Total:</span>
                                        <span className="font-bold text-blue-700 text-lg">${totalProjectedCost.toFixed(2)}</span>
                                    </div>
                                </div>
                            </div>

                            {/* Potential Savings */}
                            {totalPotentialSavings > 0 && (
                                <div className="bg-green-50 border border-green-200 rounded-lg p-4 mt-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <TrendingDown className="w-4 h-4 text-green-600" />
                                        <p className="text-green-800 text-sm font-medium">If you apply recommendations:</p>
                                    </div>
                                    <p className="text-green-900 font-bold text-lg">
                                        Save ${totalPotentialSavings.toFixed(2)}/mo
                                    </p>
                                    <p className="text-green-700 text-sm">
                                        New projected: ${(totalProjectedCost - totalPotentialSavings).toFixed(2)}/mo
                                    </p>
                                </div>
                            )}

                            {/* Footer note */}
                            <p className="text-gray-400 text-xs mt-4 text-center">
                                Updates with each new analysis
                            </p>
                        </div>
                    )}
                </div>
            )}
        </>
    );
}

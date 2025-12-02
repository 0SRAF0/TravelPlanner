import React from 'react';
import type { Itinerary } from '../../types/itinerary';
import { ItineraryDayCard } from './ItineraryDayCard';

interface ItineraryDisplayProps {
    itinerary: Itinerary;
    className?: string;
}

export const ItineraryDisplay: React.FC<ItineraryDisplayProps> = ({ itinerary, className = '' }) => {
    return (
        <div className={`bg-white/80 backdrop-blur-sm rounded-3xl shadow-xl border border-white/20 overflow-hidden ${className}`}>
            {/* Header */}
            <div className="bg-gradient-to-r from-primary/10 to-transparent p-8 border-b border-gray-100">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900 mb-2">Trip Itinerary</h2>
                        <div className="flex items-center gap-2 text-gray-600">
                            {itinerary.destination && (
                                <span className="bg-white px-3 py-1 rounded-full text-sm font-medium shadow-sm border border-gray-100">
                                    📍 {itinerary.destination}
                                </span>
                            )}
                            {itinerary.trip_duration_days && (
                                <span className="bg-white px-3 py-1 rounded-full text-sm font-medium shadow-sm border border-gray-100">
                                    🗓️ {itinerary.trip_duration_days} Days
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="flex flex-col items-end">
                        <span className={`px-4 py-1.5 rounded-full text-sm font-bold uppercase tracking-wide ${itinerary.status === 'proposed' ? 'bg-blue-100 text-blue-700' :
                            itinerary.status === 'confirmed' ? 'bg-green-100 text-green-700' :
                                'bg-gray-100 text-gray-700'
                            }`}>
                            {itinerary.status}
                        </span>
                        <span className="text-xs text-gray-400 mt-2">v{itinerary.version}</span>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="p-8">
                {itinerary.days.map((day) => (
                    <ItineraryDayCard key={day.day} day={day} />
                ))}
            </div>
        </div>
    );
};

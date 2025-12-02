import React from 'react';
import type { ItineraryItem } from '../../types/itinerary';

interface ItineraryActivityProps {
    item: ItineraryItem;
}

export const ItineraryActivity: React.FC<ItineraryActivityProps> = ({ item }) => {
    return (
        <div className="relative pl-8 py-4 group">
            {/* Timeline connector */}
            <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gray-200 group-last:bottom-auto group-last:h-8"></div>
            <div className="absolute left-[-5px] top-6 w-3 h-3 rounded-full bg-primary border-2 border-white shadow-sm z-10"></div>

            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-primary bg-secondary px-2 py-0.5 rounded">
                            {item.start_time} - {item.end_time}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full capitalize ${item.status === 'planned' ? 'bg-green-100 text-green-700' :
                            item.status === 'completed' ? 'bg-gray-100 text-gray-700' :
                                'bg-red-100 text-red-700'
                            }`}>
                            {item.status}
                        </span>
                    </div>
                </div>

                {item.name && (
                    <h4 className="text-lg font-bold text-gray-900 mb-1">{item.name}</h4>
                )}

                <p className="text-gray-700 leading-relaxed">{item.notes}</p>

                {/* Placeholder for activity details if we had them linked */}
                {/* <div className="mt-3 text-xs text-gray-400">Activity ID: {item.activity_id}</div> */}
            </div>
        </div>
    );
};

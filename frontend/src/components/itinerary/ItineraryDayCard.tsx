import React from 'react';
import type { ItineraryDay } from '../../types/itinerary';
import { ItineraryActivity } from './ItineraryActivity';

interface ItineraryDayCardProps {
    day: ItineraryDay;
}

export const ItineraryDayCard: React.FC<ItineraryDayCardProps> = ({ day }) => {
    // Parse date string (YYYY-MM-DD) manually to avoid timezone shifts
    let dayName = 'Day';
    let dateStr = '';

    if (day.date) {
        const [year, month, dayNum] = day.date.split('-').map(Number);
        const dateObj = new Date(year, month - 1, dayNum);
        dayName = new Intl.DateTimeFormat('en-US', { weekday: 'long' }).format(dateObj);
        dateStr = new Intl.DateTimeFormat('en-US', { month: 'long', day: 'numeric' }).format(dateObj);
    }

    return (
        <div className="mb-8 last:mb-0">
            <div className="flex items-center gap-4 mb-4">
                <div className="bg-primary text-white w-12 h-12 rounded-xl flex flex-col items-center justify-center shadow-lg shadow-primary/30">
                    <span className="text-xs font-bold uppercase">Day</span>
                    <span className="text-lg font-bold leading-none">{day.day}</span>
                </div>
                <div>
                    <h3 className="text-xl font-bold text-gray-900">{dayName}</h3>
                    <p className="text-gray-500">{dateStr}</p>
                </div>
            </div>

            <div className="ml-6 border-l-2 border-gray-100 pl-6 space-y-2">
                {day.items.map((item, index) => (
                    <ItineraryActivity key={`${day.day}-${index}`} item={item} />
                ))}
            </div>
        </div>
    );
};

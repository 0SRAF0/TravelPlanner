import React, { useState } from 'react';
import type { ItineraryItem } from '../../types/itinerary';
import Modal from '../modal/Modal';
import GoogleMapEmbed from '../map/GoogleMapEmbed';

interface ItineraryActivityProps {
    item: ItineraryItem;
}

export const ItineraryActivity: React.FC<ItineraryActivityProps> = ({ item }) => {
    const [isOpen, setIsOpen] = useState(false);

    const openModal = () => setIsOpen(true);
    const closeModal = () => setIsOpen(false);

    return (
        <div className="relative pl-8 py-4 group">
            {/* Timeline connector */}
            <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gray-200 group-last:bottom-auto group-last:h-8"></div>
            <div className="absolute left-[-5px] top-6 w-3 h-3 rounded-full bg-primary border-2 border-white shadow-sm z-10"></div>

            <div
                className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 hover:shadow-md transition-shadow duration-200 cursor-pointer"
                onClick={openModal}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openModal();
                    }
                }}
            >
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
                <div className="sm:flex sm:items-start sm:gap-4">
                    <div className="flex-1">
                        {item.name && (
                            <h4 className="text-lg font-bold text-gray-900 mb-1 text-left">{item.name}</h4>
                        )}
                        <p className="text-gray-700 leading-relaxed text-left">{item.notes}</p>
                    </div>
                    {item.photo_url && (
                        <img
                            src={item.photo_url as string}
                            alt={item.name || 'Activity photo'}
                            referrerPolicy="no-referrer"
                            className="mt-3 sm:mt-0 w-full sm:w-56 h-36 object-cover rounded-lg border border-gray-200"
                        />
                    )}
                </div>

                {/* Placeholder for activity details if we had them linked */}
                {/* <div className="mt-3 text-xs text-gray-400">Activity ID: {item.activity_id}</div> */}
            </div>

            {/* Activity Details Modal */}
            <Modal isOpen={isOpen} onClose={closeModal} maxWidth="700px">
                <div className="p-4 sm:p-6">
                    <div className="flex items-start justify-between mb-4">
                        <div>
                            <h3 className="text-xl font-bold text-gray-900">{item.name || 'Activity'}</h3>
                            {item.category && (
                                <div className="text-sm text-gray-600 mt-1">{item.category}</div>
                            )}
                        </div>
                        <button
                            onClick={closeModal}
                            className="text-gray-500 hover:text-gray-700 rounded p-1"
                            aria-label="Close"
                        >
                            ✕
                        </button>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mb-4">
                        <span className="font-mono text-xs font-semibold text-primary bg-secondary px-2 py-0.5 rounded">
                            {item.start_time} - {item.end_time}
                        </span>
                        {item.status && (
                            <span
                                className={`text-xs px-2 py-0.5 rounded-full capitalize ${item.status === 'planned'
                                    ? 'bg-green-100 text-green-700'
                                    : item.status === 'completed'
                                        ? 'bg-gray-100 text-gray-700'
                                        : 'bg-red-100 text-red-700'
                                    }`}
                            >
                                {item.status}
                            </span>
                        )}
                        {typeof item.rough_cost === 'number' && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                                ~${item.rough_cost}
                            </span>
                        )}
                        {typeof item.duration_min === 'number' && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700">
                                {Math.round(item.duration_min)} min
                            </span>
                        )}
                    </div>

                    {item.notes && (
                        <p className="text-gray-700 leading-relaxed mb-4 text-left">{item.notes}</p>
                    )}

                    {!!item.lat && !!item.lng && (
                        <GoogleMapEmbed
                            lat={Number(item.lat)}
                            lng={Number(item.lng)}
                            height="280px"
                            className="w-full"
                        />
                    )}
                </div>
            </Modal>
        </div>
    );
};

export interface ItineraryItem {
    activity_id: string;
    name?: string;
    start_time: string;
    end_time: string;
    notes?: string;
    status?: 'planned' | 'booked' | 'completed' | 'cancelled' | string;
    lat?: number;
    lng?: number;
    category?: string;
    rough_cost?: number;
    duration_min?: number;
}

export interface ItineraryDay {
    day: number;
    date?: string;
    summary?: string;
    daily_budget_estimate?: number;
    items: ItineraryItem[];
}

export interface Itinerary {
    trip_id: string;
    destination?: string;
    version: number;
    is_current: boolean;
    status: 'proposed' | 'approved' | 'archived' | string;
    start_date?: string;
    trip_duration_days?: number;
    timezone?: string;
    days: ItineraryDay[];
    created_at?: { $date: string } | string | Date;
    updated_at?: { $date: string } | string | Date;
}

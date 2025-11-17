export interface Activity {
  trip_id: string;
  name: string;
  category:
    | "Food"
    | "Nightlife"
    | "Adventure"
    | "Culture"
    | "Relax"
    | "Nature"
    | "Other"
    | string;
  rough_cost?: number | null;
  duration_min?: number | null;
  lat?: number | null;
  lng?: number | null;
  tags: string[];
  fits: string[]; // user ids or names
  score: number; // 0..1
  rationale: string;
  created_at?: string;
  updated_at?: string;
}

export interface VoteRequest {
  trip_id: string;
  activity_name: string;
  user_id: string;
  vote: "up" | "down";
}

export interface VoteResponse {
  success: boolean;
  message?: string;
}

import { API } from './api';
import type { Activity, VoteRequest, VoteResponse } from '../types/activity';
import { authService } from './authService';

export interface GetActivitiesParams {
  trip_id: string;
  category?: string;
  min_score?: number;
  limit?: number;
}

export const activityService = {
  async getActivities(params: GetActivitiesParams): Promise<Activity[]> {
    const url = new URL(API.activities.list);
    url.searchParams.set('trip_id', params.trip_id);
    if (params.category) url.searchParams.set('category', params.category);
    if (typeof params.min_score === 'number') url.searchParams.set('min_score', String(params.min_score));
    if (typeof params.limit === 'number') url.searchParams.set('limit', String(params.limit));

    const token = authService.getToken?.();
    const response = await fetch(url.toString(), {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(text || 'Failed to load activities');
    }
    return response.json();
  },

  async vote(body: VoteRequest): Promise<VoteResponse> {
    // Optional endpoint; gracefully handle if missing
    const token = authService.getToken?.();
    const response = await fetch(API.activities.vote, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      // Return a consistent error
      const text = await response.text().catch(() => '');
      throw new Error(text || 'Voting failed');
    }
    return response.json();
  },
};



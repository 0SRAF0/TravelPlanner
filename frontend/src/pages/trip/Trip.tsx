import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Button from '../../components/button/Button';
import Notification from '../../components/notification/Notification';
import { API } from '../../services/api';
import ConfirmProceedModal from './components/ConfirmProceedModal.tsx';

interface Member {
  user_id: string;
  name: string;
  picture?: string;
  has_submitted_preferences: boolean;
}

interface TripData {
  trip_id: string;
  trip_code: string;
  trip_name: string;
  destination?: string;
  trip_duration_days?: number;
  status: string;
  orchestrator_status?: string;
  members: string[];
  members_with_preferences: string[];
  member_details: Member[];
  creator_id: string;
}

export default function Trip() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const [trip, setTrip] = useState<TripData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    type?: 'success' | 'error' | 'warning';
  } | null>(null);
  const [processingAllIn, setProcessingAllIn] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [pendingMembers, setPendingMembers] = useState<{ name: string; picture?: string }[]>([]);
  const fetchTripDetailsRef = useRef<(() => Promise<void>) | null>(null);

  const currentUser = JSON.parse(localStorage.getItem('user_info') || '{}');
  const hasSubmitted = trip?.members_with_preferences.includes(currentUser.id) || false;

  const fetchTripDetails = useCallback(async () => {
    // Protect against invalid tripId values (e.g. the literal string 'undefined')
    if (!tripId || tripId === 'undefined') {
      setError('Invalid trip id');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const url = new URL(API.trip.get);
      url.searchParams.set('trip_id', String(tripId));
      const response = await fetch(url.toString());
      const result = await response.json();

      if (result.code === 0 && result.data) {
        setTrip(result.data);
      } else {
        throw new Error(result.msg || 'Failed to load trip');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trip');
    } finally {
      setLoading(false);
    }
  }, [tripId]);

  // Keep ref updated
  useEffect(() => {
    fetchTripDetailsRef.current = fetchTripDetails;
  }, [fetchTripDetails]);

  useEffect(() => {
    fetchTripDetails();
  }, [fetchTripDetails]);

  // WebSocket listener for all-in navigation broadcast and member updates
  useEffect(() => {
    if (!tripId || tripId === 'undefined') return;

    const ws = new WebSocket(`ws://localhost:8060/chat/${tripId}`);

    ws.onopen = () => {
      console.log('[Trip] WebSocket connected');
      // Send a ping message to complete the WebSocket handshake loop on the backend
      ws.send(
        JSON.stringify({
          type: 'ping',
          senderId: currentUser.id || 'anonymous',
          senderName: currentUser.name || 'Anonymous',
          content: '',
        }),
      );
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[Trip] WebSocket message received:', data);

        // Listen for navigate_to_chat broadcast
        if (data.type === 'navigate_to_chat') {
          console.log('[Trip] Received navigate_to_chat broadcast, navigating...');
          navigate(`/trip/chat/${tripId}`);
        }

        // Refresh trip details when a new member joins
        if (data.type === 'member_joined') {
          console.log('[Trip] New member joined, refreshing trip details...');
          fetchTripDetailsRef.current?.();
        }

        // Refresh trip details when someone submits preferences
        if (data.type === 'preference_submitted') {
          console.log('[Trip] Member submitted preferences, refreshing trip details...');
          fetchTripDetailsRef.current?.();
        }
      } catch (error) {
        console.error('[Trip] WebSocket message parse error:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('[Trip] WebSocket error:', error);
    };

    return () => {
      ws.close();
    };
  }, [tripId, navigate]);

  const handleSetPreferences = () => {
    navigate(`/trip/preferences/${tripId}`);
  };

  const handleCopyCode = () => {
    if (trip?.trip_code) {
      navigator.clipboard.writeText(trip.trip_code);
      setToast({ message: 'Trip code copied!', type: 'success' });
    }
  };

  const startAllIn = async () => {
    setProcessingAllIn(true);
    try {
      const response = await fetch(API.trip.allIn, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trip_id: tripId }),
      });

      const result = await response.json();

      if (result.code === 0) {
        // Wait a moment to allow the backend to broadcast to other users
        // before we navigate (otherwise we might close our WebSocket too early)
        await new Promise((resolve) => setTimeout(resolve, 300));
        navigate(`/trip/chat/${tripId}`);
      } else {
        setToast({
          message: result.msg || 'Failed to start planning',
          type: 'error',
        });
      }
    } catch (err) {
      setToast({
        message: err instanceof Error ? err.message : 'Failed to process',
        type: 'error',
      });
    } finally {
      setProcessingAllIn(false);
    }
  };

  const handleAllIn = async () => {
    if (!trip) return;

    const notSubmitted = trip.member_details.filter((m) => !m.has_submitted_preferences);

    if (notSubmitted.length > 0) {
      setPendingMembers(notSubmitted.map((m) => ({ name: m.name, picture: m.picture })));
      setShowConfirm(true);
      return;
    }

    await startAllIn();
  };
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-gray-200 border-t-blue-500 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Loading trip details...</p>
        </div>
      </div>
    );
  }

  if (error || !trip) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-4">😕</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Trip Not Found</h2>
          <p className="text-gray-600 mb-6">{error || 'This trip does not exist'}</p>
          <Button text="Back to Dashboard" onClick={() => navigate('/dashboard')} />
        </div>
      </div>
    );
  }

  const allSubmitted =
    trip.members.length > 0 && trip.members.length === trip.members_with_preferences.length;
  const canTriggerAllIn = trip.members_with_preferences.length > 0;

  return (
    <div className="min-h-screen py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-1">{trip.trip_name}</h1>
              {trip.destination && <p className="text-lg text-gray-600">📍 {trip.destination}</p>}
              {trip.trip_duration_days && (
                <p className="text-sm text-gray-500">🗓️ {trip.trip_duration_days} days</p>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 bg-gray-50 px-4 py-2 rounded-lg">
                <span className="text-sm text-gray-600">Trip Code:</span>
                <span className="font-mono font-bold text-lg">{trip.trip_code}</span>
                <button
                  onClick={handleCopyCode}
                  className="p-1 hover:bg-gray-200 rounded"
                  title="Copy code"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                    />
                  </svg>
                </button>
              </div>
              <div className="text-xs text-gray-500 text-right">
                Status: {trip.status.replace('_', ' ')}
              </div>
            </div>
          </div>
        </div>

        {/* Member Status */}
        <div className="bg-white rounded-2xl shadow-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-900">
              Group Members ({trip.members.length})
            </h2>
            {!hasSubmitted && (
              <Button text="Set My Preferences" onClick={handleSetPreferences} size="base" />
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {trip.member_details.map((member) => (
              <div
                key={member.user_id}
                className={`flex items-center gap-3 p-3 rounded-xl border-2 ${
                  member.has_submitted_preferences
                    ? 'border-green-200 bg-green-50'
                    : 'border-gray-200 bg-gray-50'
                }`}
              >
                {member.picture ? (
                  <img src={member.picture} alt={member.name} className="w-10 h-10 rounded-full" />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-gray-300 flex items-center justify-center text-gray-600 font-bold">
                    {member.name[0]}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-900 truncate">{member.name}</div>
                  <div className="text-xs text-gray-500">
                    {member.has_submitted_preferences ? '✓ Submitted' : '⏳ Pending'}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* All In Button / Go to Chat */}
          {canTriggerAllIn && (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-gray-600">
                    {trip.status === 'planning'
                      ? '🤖 AI is planning your trip! Check the chat to see progress.'
                      : allSubmitted
                        ? '🎉 Everyone has submitted! Ready to generate your itinerary.'
                        : `⏳ ${trip.members_with_preferences.length}/${trip.members.length} members have submitted preferences.`}
                  </p>
                </div>
                {['planning', 'consensus'].includes(trip.status) ||
                ['running', 'paused', 'completed'].includes(trip.orchestrator_status || '') ? (
                  <Button
                    text="Go to Chat 💬"
                    onClick={() => navigate(`/trip/chat/${tripId}`)}
                    size="lg"
                  />
                ) : (
                  <Button
                    text={processingAllIn ? 'Processing...' : "Let's Go! 🚀"}
                    onClick={handleAllIn}
                    size="lg"
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <Notification
        isVisible={!!toast}
        message={toast?.message || ''}
        type={toast?.type}
        onClose={() => setToast(null)}
      />
      <ConfirmProceedModal
        isOpen={showConfirm}
        pendingMembers={pendingMembers}
        isProcessing={processingAllIn}
        onClose={() => setShowConfirm(false)}
        onConfirm={async () => {
          setShowConfirm(false);
          await startAllIn();
        }}
      />
    </div>
  );
}

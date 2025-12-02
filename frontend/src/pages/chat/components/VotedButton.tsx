import { useState, useEffect } from 'react';
import Button from '../../../components/button/Button.tsx';
import { API } from '../../../services/api.ts';

interface VotedButtonProps {
  tripId: string;
  currentPhase: string;
  currentUserId: string;
  usersReady: string[];
  totalUsers: number;
  buttonText?: string; // "Voted" or "Approved"
  onStatusChange?: (allReady: boolean) => void;
}

export default function VotedButton({
  tripId,
  currentPhase,
  currentUserId,
  usersReady,
  totalUsers,
  buttonText = 'Voted',
  onStatusChange,
}: VotedButtonProps) {
  const [hasVoted, setHasVoted] = useState(false);
  const [loading, setLoading] = useState(false);

  // Check if current user has voted
  useEffect(() => {
    setHasVoted(usersReady.includes(currentUserId));
  }, [usersReady, currentUserId]);

  const handleToggle = async () => {
    setLoading(true);

    try {
      const endpoint = hasVoted ? API.trip.unmarkReady(tripId) : API.trip.markReady(tripId);

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          phase: currentPhase,
        }),
      });

      const result = await response.json();

      if (result.code === 0) {
        setHasVoted(!hasVoted);

        // Notify parent if all users ready
        if (onStatusChange) {
          onStatusChange(result.data.all_ready);
        }
      } else {
        console.error('Failed to toggle voted status:', result.msg);
      }
    } catch (error) {
      console.error('Failed to toggle voted status:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        text={loading ? 'Loading...' : hasVoted ? `Un-${buttonText}` : buttonText}
        onClick={handleToggle}
        disabled={loading}
        color={hasVoted ? 'var(--color-secondary)' : 'var(--color-primary)'}
      />

      <div className="text-sm text-center text-gray-600">
        Ready: {usersReady.length}/{totalUsers}
        {usersReady.length >= totalUsers && (
          <span className="ml-2 text-green-600 font-semibold">✓ All ready!</span>
        )}
      </div>
    </div>
  );
}

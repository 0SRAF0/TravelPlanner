import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Modal from '../../../components/modal/Modal.tsx';
import Button from '../../../components/button';
import Input from '../../../components/input';
import Notification from '../../../components/notification/Notification.tsx';
import { API } from '../../../services/api.ts';

interface CreateTripModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (tripData: { trip_id: string; trip_code: string; trip_name: string }) => void;
}

export default function CreateTripModal({ isOpen, onClose, onSuccess }: CreateTripModalProps) {
  const navigate = useNavigate();
  const [tripName, setTripName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!tripName.trim()) {
      setError('Please enter a trip name');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const user = JSON.parse(localStorage.getItem('user_info') || '{}');

      const response = await fetch(API.trip.create, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          trip_name: tripName.trim(),
          creator_id: user.id,
          destination: null,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create trip');
      }

      const result = await response.json();

      if (result.code === 0 && result.data) {
        onSuccess?.(result.data);
        setTripName('');
        onClose();

        // Redirect to preferences page
        navigate(`/trip/preferences/${result.data.trip_id}`, {
          state: { tripName: result.data.trip_name },
        });
      } else {
        throw new Error(result.msg || 'Failed to create trip');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create trip');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose}>
        <div className="space-y-8 px-2 py-4">
          {/* Header - Centered */}
          <div className="text-center">
            <h2 className="text-3xl font-bold text-gray-900 mb-2">Create New Trip</h2>
            <p className="text-gray-600">Start planning your next adventure</p>
          </div>

          {/* Form - More spacing */}
          <div className="space-y-6 py-4">
            <div>
              <label className="block text-sm text-gray-700 font-semibold mb-3">Trip Name *</label>
              <Input
                type="text"
                placeholder="e.g., Summer Japan Trip"
                value={tripName}
                onChange={(e) => setTripName(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>

          {/* Buttons - Better hierarchy and spacing */}
          <div className="flex flex-col gap-3 pt-4">
            <div className="w-full">
              <Button
                text={loading ? 'Creating...' : 'Create Trip'}
                onClick={handleSubmit}
                size="lg"
                disabled={loading}
              />
            </div>
            <button
              onClick={onClose}
              disabled={loading}
              className="w-full px-4 py-2.5 text-sm text-gray-600 bg-transparent hover:bg-gray-50 rounded-xl disabled:opacity-50 font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </Modal>

      <Notification
        isVisible={!!error}
        message={error || ''}
        type="error"
        onClose={() => setError(null)}
      />
    </>
  );
}

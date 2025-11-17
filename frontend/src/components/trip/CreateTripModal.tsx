import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Modal from "../modal/Modal.tsx";
import Button from "../button";
import Input from "../input";

interface CreateTripModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (tripData: {
    trip_id: string;
    trip_code: string;
    trip_name: string;
  }) => void;
}

export default function CreateTripModal({
  isOpen,
  onClose,
  onSuccess,
}: CreateTripModalProps) {
  const navigate = useNavigate();
  const [tripName, setTripName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!tripName.trim()) {
      setError("Please enter a trip name");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const user = JSON.parse(localStorage.getItem("user_info") || "{}");

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/trips/create`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            trip_name: tripName,
            creator_id: user.id,
          }),
        }
      );

      if (!response.ok) {
        throw new Error("Failed to create trip");
      }

      const result = await response.json();

      if (result.code === 0 && result.data) {
        onSuccess?.(result.data);
        setTripName("");
        onClose();

        // Redirect to preferences page
        navigate(`/trip/${result.data.trip_id}/preferences`, {
          state: { tripName: result.data.trip_name },
        });
      } else {
        throw new Error(result.msg || "Failed to create trip");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create trip");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Create New Trip</h2>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Trip Name *
            </label>
            <Input
              type="text"
              placeholder="e.g., Summer Japan Trip"
              value={tripName}
              onChange={(e) => setTripName(e.target.value)}
              disabled={loading}
            />
          </div>
          <p className="text-sm text-gray-600">
            You'll set your travel preferences on the next step.
          </p>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="flex-1 px-4 py-2 text-gray-700 bg-gray-100 rounded-xl hover:bg-gray-200 disabled:opacity-50 font-medium"
          >
            Cancel
          </button>
          <Button
            text={loading ? "Creating..." : "Create Trip"}
            onClick={handleSubmit}
            size="base"
          />
        </div>
      </div>
    </Modal>
  );
}

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../../components/button/Button";
import Input from "../../components/input/Input";
import CreateTripModal from "../../components/trip/CreateTripModal";
import TripCodeModal from "../../components/trip/TripCodeModal";
import Notification from "../../components/notification/Notification";

interface Trip {
  trip_id: string;
  trip_name: string;
  trip_code: string;
  destination?: string;
  status: string;
  members: string[];
}

const Dashboard = () => {
  const navigate = useNavigate();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [tripCode, setTripCode] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showCodeModal, setShowCodeModal] = useState(false);
  const [newTripData, setNewTripData] = useState<{
    trip_id: string;
    trip_code: string;
    trip_name: string;
  } | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [tripToDelete, setTripToDelete] = useState<string | null>(null);
  const currentUser = JSON.parse(localStorage.getItem("user_info") || "{}");

  useEffect(() => {
    fetchUserTrips();
  }, []);

  const fetchUserTrips = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/trips/user/${currentUser.id}`
      );
      const result = await response.json();

      if (result.code === 0) {
        setTrips(result.data);
      }
    } catch (err) {
      console.error("Failed to load trips:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleJoinTrip = async () => {
    if (!tripCode.trim()) {
      setToast({ message: "Please enter a trip code", type: "error" });
      return;
    }

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/trips/join`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            trip_code: tripCode.toUpperCase(),
            user_id: currentUser.id,
          }),
        }
      );

      const result = await response.json();

      if (result.code === 0 && result.data) {
        setToast({
          message: `Joined ${result.data.trip_name}!`,
          type: "success",
        });
        setTripCode("");
        // Navigate to trip detail
        setTimeout(() => {
          navigate(`/trip/${result.data.trip_id}`);
        }, 1000);
      } else {
        throw new Error(result.msg || "Failed to join trip");
      }
    } catch (err) {
      setToast({
        message: err instanceof Error ? err.message : "Failed to join trip",
        type: "error",
      });
    }
  };

  const handleCreateSuccess = (data: {
    trip_id: string;
    trip_code: string;
    trip_name: string;
  }) => {
    setNewTripData(data);
    // Don't show code modal - user is redirected to preferences in CreateTripModal
    fetchUserTrips(); // Refresh trips list
  };

  const handleGoToPreferences = () => {
    if (newTripData) {
      navigate(`/trip/${newTripData.trip_id}/preferences`);
    }
  };

  const handleTripClick = (tripId: string) => {
    navigate(`/trip/${tripId}`);
  };

  const handleDeleteClick = (e: React.MouseEvent, tripId: string) => {
    e.stopPropagation(); // Prevent trip click
    setTripToDelete(tripId);
    setShowDeleteConfirm(true);
  };

  const confirmDelete = async () => {
    if (!tripToDelete) return;

    const currentUser = JSON.parse(localStorage.getItem("user_info") || "{}");
    if (!currentUser || !currentUser.id) {
      setToast({ message: "User not found", type: "error" });
      return;
    }

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/trips/${tripToDelete}?user_id=${
          currentUser.id
        }`,
        { method: "DELETE" }
      );

      const data = await response.json();

      if (data.code === 0) {
        setToast({ message: "Trip deleted successfully", type: "success" });
        setShowDeleteConfirm(false);
        setTripToDelete(null);
        fetchUserTrips(); // Refresh trips list
      } else {
        setToast({
          message: data.msg || "Failed to delete trip",
          type: "error",
        });
      }
    } catch (error) {
      console.error("Error deleting trip:", error);
      setToast({ message: "Failed to delete trip", type: "error" });
    }
  };

  const cancelDelete = () => {
    setShowDeleteConfirm(false);
    setTripToDelete(null);
  };

  return (
    <div className="min-h-screen px-6 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Mobile Layout */}
        <div className="lg:hidden space-y-6">
          {/* Buttons Section - Mobile */}
          <div className="space-y-4">
            {/* Join Trip */}
            <div className="bg-white rounded-2xl shadow-md p-6 space-y-3">
              <h3 className="text-lg font-bold text-gray-900">Join a Trip</h3>
              <Input
                type="text"
                placeholder="Enter trip code"
                value={tripCode}
                onChange={(e) => setTripCode(e.target.value.toUpperCase())}
                size="lg"
              />
              <Button text="Join Trip" onClick={handleJoinTrip} size="lg" />
            </div>

            {/* Create Trip */}
            <div className="bg-white rounded-2xl shadow-md p-6">
              <h3 className="text-lg font-bold text-gray-900 mb-3">
                Start Planning
              </h3>
              <Button
                text="Create Trip"
                onClick={() => setShowCreateModal(true)}
                size="lg"
              />
            </div>
          </div>

          {/* Saved Trips - Mobile */}
          <div className="space-y-3">
            <h2 className="text-xl font-bold text-gray-900">Your Trips</h2>
            {loading ? (
              <div className="text-center py-8">
                <div className="w-8 h-8 border-4 border-gray-200 border-t-blue-500 rounded-full animate-spin mx-auto"></div>
              </div>
            ) : trips.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <p className="text-lg mb-2">No trips yet</p>
                <p className="text-sm">Create or join a trip to get started!</p>
              </div>
            ) : (
              <div className="space-y-3">
                {trips.map((trip) => (
                  <div
                    key={trip.trip_id}
                    onClick={() => handleTripClick(trip.trip_id)}
                    className="relative bg-gray-100 rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                  >
                    <button
                      onClick={(e) => handleDeleteClick(e, trip.trip_id)}
                      className="absolute top-3 right-3 w-6 h-6 flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-colors"
                      aria-label="Delete trip"
                    >
                      ✕
                    </button>
                    <p className="text-lg font-semibold text-gray-700">
                      {trip.trip_name}
                    </p>
                    {trip.destination && (
                      <p className="text-sm text-gray-500 mt-1">
                        📍 {trip.destination}
                      </p>
                    )}
                    <p className="text-xs text-gray-400 mt-2">
                      {trip.members.length} members
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Desktop/Tablet Layout */}
        <div className="hidden lg:flex lg:gap-8">
          {/* Left Side - Buttons (30%) */}
          <div className="lg:w-[30%] space-y-6">
            {/* Join Trip */}
            <div className="bg-white rounded-2xl shadow-md p-6 space-y-4">
              <h3 className="text-xl font-bold text-gray-900">Join a Trip</h3>
              <Input
                type="text"
                placeholder="Enter trip code"
                value={tripCode}
                onChange={(e) => setTripCode(e.target.value.toUpperCase())}
                size="lg"
              />
              <Button text="Join Trip" onClick={handleJoinTrip} size="lg" />
            </div>

            {/* Create Trip */}
            <div className="bg-white rounded-2xl shadow-md p-6 space-y-4">
              <h3 className="text-xl font-bold text-gray-900">
                Start Planning
              </h3>
              <Button
                text="Create Trip"
                onClick={() => setShowCreateModal(true)}
                size="lg"
              />
            </div>
          </div>

          {/* Right Side - Saved Trips Grid (70%) */}
          <div className="lg:w-[70%] space-y-4">
            <h2 className="text-2xl font-bold text-gray-900">Your Trips</h2>
            {loading ? (
              <div className="text-center py-12">
                <div className="w-12 h-12 border-4 border-gray-200 border-t-blue-500 rounded-full animate-spin mx-auto"></div>
              </div>
            ) : trips.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <p className="text-xl mb-2">No trips yet</p>
                <p>Create or join a trip to get started!</p>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-4">
                {trips.map((trip) => (
                  <div
                    key={trip.trip_id}
                    onClick={() => handleTripClick(trip.trip_id)}
                    className="relative bg-gray-100 rounded-xl p-8 shadow-sm hover:shadow-lg transition-shadow cursor-pointer"
                  >
                    <button
                      onClick={(e) => handleDeleteClick(e, trip.trip_id)}
                      className="absolute top-3 right-3 w-6 h-6 flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-colors"
                      aria-label="Delete trip"
                    >
                      ✕
                    </button>
                    <p className="text-lg font-semibold text-gray-700 text-center mb-2">
                      {trip.trip_name}
                    </p>
                    {trip.destination && (
                      <p className="text-sm text-gray-500 text-center">
                        📍 {trip.destination}
                      </p>
                    )}
                    <p className="text-xs text-gray-400 text-center mt-2">
                      {trip.members.length} members
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      <CreateTripModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={handleCreateSuccess}
      />

      <TripCodeModal
        isOpen={showCodeModal}
        tripCode={newTripData?.trip_code || ""}
        tripName={newTripData?.trip_name || ""}
        onClose={() => setShowCodeModal(false)}
        onGoToPreferences={handleGoToPreferences}
      />

      <Notification
        isVisible={!!toast}
        message={toast?.message || ""}
        type={toast?.type}
        onClose={() => setToast(null)}
      />

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-xl font-bold text-gray-900 mb-3">
              Delete Trip?
            </h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this trip? This action cannot be
              undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={cancelDelete}
                className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="px-4 py-2 text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;

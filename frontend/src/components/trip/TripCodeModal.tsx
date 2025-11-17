import { useState } from "react";
import Modal from "../modal/Modal.tsx";
import Button from "../button/Button.tsx";

interface TripCodeModalProps {
  isOpen: boolean;
  tripCode: string;
  tripName: string;
  onClose: () => void;
  onGoToPreferences: () => void;
}

export default function TripCodeModal({
  isOpen,
  tripCode,
  tripName,
  onClose,
  onGoToPreferences,
}: TripCodeModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(tripCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <div className="space-y-6 text-center">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
          <svg
            className="w-8 h-8 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 13l4 4L19 7"
            />
          </svg>
        </div>

        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Trip Created!
          </h2>
          <p className="text-gray-600">{tripName}</p>
        </div>

        <div className="bg-gray-50 rounded-xl p-6">
          <p className="text-sm text-gray-600 mb-3">
            Share this code with your friends:
          </p>
          <div className="flex items-center justify-center gap-3">
            <div className="text-4xl font-bold tracking-wider text-gray-900 font-mono">
              {tripCode}
            </div>
            <button
              onClick={handleCopy}
              className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
              title="Copy code"
            >
              {copied ? (
                <svg
                  className="w-5 h-5 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              ) : (
                <svg
                  className="w-5 h-5 text-gray-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              )}
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <Button
            text="Set My Preferences"
            onClick={onGoToPreferences}
            size="lg"
          />
          <button
            onClick={onClose}
            className="w-full text-gray-600 hover:text-gray-900 text-sm font-medium"
          >
            I'll do this later
          </button>
        </div>
      </div>
    </Modal>
  );
}

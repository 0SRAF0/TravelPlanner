import { useState } from 'react';
import { ChatBox } from './ChatBox.tsx';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faXmark, faComments } from '@fortawesome/free-solid-svg-icons';

export const ChatButton = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 w-14 h-14 bg-primary hover:bg-primary text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center z-40 group"
        aria-label="Open AI chat"
      >
        {isOpen ? (
          <FontAwesomeIcon icon={faXmark} className="w-6 h-6" />
        ) : (
          <FontAwesomeIcon icon={faComments} className="w-6 h-6" />
        )}
      </button>
      <ChatBox isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

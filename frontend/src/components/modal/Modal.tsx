import React from 'react';

interface ModalProps {
  isOpen: boolean;
  mask?: boolean;
  backgroundColor?: string;
  width?: string;
  maxWidth?: string;
  children: React.ReactNode;
  onClose: () => void;
  unstyled?: boolean; // Allow children to control all styling
}

export default function Modal({
  isOpen,
  onClose,
  mask = true,
  backgroundColor = '#F6F7FA',
  width,
  maxWidth,
  children,
  unstyled = false,
}: ModalProps) {
  if (!isOpen) return null;

  const handleOverlayClick = () => {
    onClose();
  };

  const modalStyle = {
    backgroundColor,
    ...(width && { width }),
    ...(maxWidth && { maxWidth })
  };

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      {mask && (
        <div className="absolute inset-0 bg-black/25" onClick={handleOverlayClick} />
      )}
      
      {unstyled ? (
        <div 
          className="relative mx-4"
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </div>
      ) : (
        <div 
          className="relative bg-white rounded-3xl px-6 py-12 max-w-md w-full mx-4"
          style={modalStyle}
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </div>
      )}
    </div>
  );
}

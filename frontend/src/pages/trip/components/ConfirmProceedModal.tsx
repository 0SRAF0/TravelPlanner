import Modal from '../../../components/modal/Modal.tsx';
import Button from '../../../components/button/Button.tsx';

interface PendingMember {
	name: string;
	picture?: string;
}

interface ConfirmProceedModalProps {
	isOpen: boolean;
	onClose: () => void;
	onConfirm: () => void;
	pendingMembers: PendingMember[];
	isProcessing?: boolean;
}

export default function ConfirmProceedModal({
	isOpen,
	onClose,
	onConfirm,
	pendingMembers,
	isProcessing = false,
}: ConfirmProceedModalProps) {
	return (
		<Modal isOpen={isOpen} onClose={onClose}>
			<div className="space-y-6">
				<div className="w-14 h-14 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center mx-auto">
					<svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M10.29 3.86l-7.4 12.84A2 2 0 004.53 20h14.94a2 2 0 001.73-3.3L13.8 3.86a2 2 0 00-3.51 0z" />
					</svg>
				</div>

				<h3 className="text-xl font-bold text-gray-900 text-center leading-snug">
					Not everyone has submitted preferences yet
				</h3>

				<div className="space-y-3">
					{pendingMembers.length > 0 && (
						<div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
							<p className="text-xs font-medium text-amber-800 mb-2 uppercase tracking-wide">
								Waiting on
							</p>
							<div className="flex flex-wrap gap-2">
								{pendingMembers.map((m, idx) => (
									<div key={`${m.name}-${idx}`} className="flex items-center gap-2 bg-white border border-amber-200 rounded-full pr-3 pl-1 py-1 shadow-sm">
										{m.picture ? (
											<img src={m.picture} alt={m.name} className="w-7 h-7 rounded-full object-cover" />
										) : (
											<div className="w-7 h-7 rounded-full bg-gray-300 flex items-center justify-center text-gray-700 text-xs font-semibold">
												{m.name.charAt(0)}
											</div>
										)}
										<span className="text-sm text-gray-800">{m.name}</span>
									</div>
								))}
							</div>
						</div>
					)}
					<p className="text-sm text-gray-600 text-center">
						Proceed anyway? The AI will work with available preferences.
					</p>
				</div>

				<div className="flex gap-3 justify-end">
					<button
						onClick={onClose}
						disabled={isProcessing}
						className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
					>
						Cancel
					</button>
					<Button
						text={isProcessing ? 'Processing...' : 'OK'}
						onClick={onConfirm}
						size="base"
					/>
				</div>
			</div>
		</Modal>
	);
}



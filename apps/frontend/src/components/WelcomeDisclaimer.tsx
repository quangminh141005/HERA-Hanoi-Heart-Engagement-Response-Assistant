import { Info, ShieldCheck } from 'lucide-react';

export function WelcomeDisclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <section className={`welcome-disclaimer${compact ? ' welcome-disclaimer-compact' : ''}`} aria-label="Phạm vi hỗ trợ">
      <ShieldCheck size={20} aria-hidden="true" />
      <div>
        <strong>HERA hỗ trợ thông tin hành chính, không chẩn đoán hoặc kê thuốc.</strong>
        <p>
          Không gửi CCCD, số thẻ BHYT, số điện thoại hoặc bệnh án. Lịch làm việc không đồng nghĩa còn suất khám.
        </p>
      </div>
      <Info size={18} aria-hidden="true" />
    </section>
  );
}

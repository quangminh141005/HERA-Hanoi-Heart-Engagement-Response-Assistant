import { PhoneCall, Siren } from 'lucide-react';

function emergencyNumber(): string {
  const configured = import.meta.env.VITE_EMERGENCY_HOTLINE?.trim() || '115';
  return /^[+\d][\d\s.-]*$/.test(configured) ? configured : '115';
}

export function EmergencyCard() {
  const hotline = emergencyNumber();
  return (
    <section className="emergency-card" role="alert" aria-label="Hướng dẫn cấp cứu">
      <Siren size={24} aria-hidden="true" />
      <div>
        <h3>Ưu tiên hỗ trợ cấp cứu</h3>
        <p>Nếu tình trạng đang xảy ra hoặc xấu đi, hãy gọi cấp cứu ngay. HERA không thực hiện chẩn đoán.</p>
        <a href={`tel:${hotline.replace(/[^+\d]/g, '')}`}>
          <PhoneCall size={18} aria-hidden="true" />
          Gọi {hotline}
        </a>
      </div>
    </section>
  );
}
